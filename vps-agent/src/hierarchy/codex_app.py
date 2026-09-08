"""Small, defensive client for the Codex app-server protocol.

The app-server is a newline-delimited JSON protocol spoken by the ``codex``
CLI.  This module intentionally owns only transport and turn lifecycle.  It
does not read or copy Codex credentials; the child process resolves its own
``CODEX_HOME``/authentication configuration.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


class CodexAppError(RuntimeError):
    """A transport, protocol, or terminal app-server failure."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        method: str | None = None,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.method = method
        self.data = data


@dataclass(frozen=True)
class CodexTurnResult:
    """The projected terminal result of one Codex turn."""

    text: str
    status: str
    thread_id: str
    turn_id: str


@dataclass(frozen=True)
class _ProcessIdentity:
    pid: int
    pgid: int
    starttime: str | None


EventCallback = Callable[[dict[str, Any]], None]

_STATUS_CACHE_TTL = 10.0
_status_cache_lock = threading.Lock()
_status_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}

_CHILD_ENV_KEYS = frozenset(
    {
        "HOME", "PATH", "CODEX_HOME",
        "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
        "TMPDIR", "TMP", "TEMP",
    }
)


def _safe_child_environment(
    codex_home: str | None, overrides: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Build the narrow environment a model-controlled child may inherit."""
    env = {key: value for key, value in os.environ.items() if key in _CHILD_ENV_KEYS}
    if overrides:
        env.update({
            str(key): str(value)
            for key, value in overrides.items()
            if str(key) in _CHILD_ENV_KEYS
        })
    if codex_home is not None:
        env["CODEX_HOME"] = codex_home
    env.setdefault("PATH", os.defpath)
    return env


def codex_status(
    binary: str = "codex",
    codex_home: str | os.PathLike[str] | None = None,
    timeout: float = 5.0,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return bounded, non-secret Codex availability/login status.

    Authentication is delegated to ``codex login status``; this function never
    opens or parses ``auth.json`` and does not return command output.
    """
    binary_value = str(binary)
    if not binary or "\x00" in binary_value:
        return {"binary": str(binary), "available": False, "authenticated": None}
    try:
        home = CodexAppClient._validate_codex_home(codex_home)
    except ValueError:
        return {"binary": str(binary), "available": False, "authenticated": None}
    child_env = _safe_child_environment(home, environment)
    cache_key = (binary_value, home, tuple(sorted(child_env.items())))
    now = time.monotonic()
    with _status_cache_lock:
        cached = _status_cache.get(cache_key)
        if cached is not None and now - cached[0] < _STATUS_CACHE_TTL:
            return dict(cached[1])
    try:
        result = subprocess.run(
            [binary_value, "login", "status"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=max(float(timeout), 0.01),
            env=child_env,
            check=False,
        )
    except FileNotFoundError:
        status = {"binary": binary_value, "available": False, "authenticated": None}
        with _status_cache_lock:
            _status_cache[cache_key] = (time.monotonic(), status)
        return dict(status)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        status = {"binary": binary_value, "available": True, "authenticated": None}
        with _status_cache_lock:
            _status_cache[cache_key] = (time.monotonic(), status)
        return dict(status)
    status = {
        "binary": binary_value,
        "available": True,
        "authenticated": result.returncode == 0,
    }
    with _status_cache_lock:
        _status_cache[cache_key] = (time.monotonic(), status)
    return dict(status)


def public_status(
    binary: str = "codex",
    codex_home: str | os.PathLike[str] | None = None,
    timeout: float = 5.0,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compatibility name for the server's non-secret status endpoint."""
    return codex_status(binary, codex_home, timeout, environment)


class CodexAppClient:
    """Thread-safe request speaker and single-turn app-server adapter.

    One child process is reused for all turns.  A client supports one active
    turn at a time; the app-server itself may emit events for other threads, so
    the turn loop filters notifications by both thread and turn identity.
    """

    _MAX_STDERR_LINES = 200
    _MAX_STDERR_LINE_CHARS = 4_000
    _POLL_INTERVAL = 0.1

    def __init__(
        self,
        binary: str = "codex",
        codex_home: str | os.PathLike[str] | None = None,
        timeout: float = 120.0,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if not binary or "\x00" in str(binary):
            raise ValueError("binary must be a non-empty path/name")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.binary = str(binary)
        self.codex_home = self._validate_codex_home(codex_home)
        self.timeout = float(timeout)
        self.environment = {str(key): str(value) for key, value in (environment or {}).items()}

        self._state_lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._turn_lock = threading.Lock()
        self._next_request_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._events: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue()
        self._server_requests: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=self._MAX_STDERR_LINES)
        self._proc: Any = None
        self._initialized = False
        self._closed = False
        self._known_threads: set[str] = set()
        self._reader_threads: list[threading.Thread] = []
        self._generation = 0
        self._proc_identity: _ProcessIdentity | None = None

    @staticmethod
    def _validate_codex_home(value: str | os.PathLike[str] | None) -> str | None:
        if value is None:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("codex_home must be an absolute path")
        if "\x00" in str(path):
            raise ValueError("codex_home contains NUL")
        return str(path)

    def start(self) -> None:
        """Spawn and initialize one app-server process, idempotently."""
        with self._start_lock:
            with self._state_lock:
                if self._closed:
                    raise CodexAppError("Codex app client is closed")
                proc = self._proc
                if proc is not None and proc.poll() is None and self._initialized:
                    return
                if proc is not None:
                    self._shutdown_process(proc)
                self._initialized = False

            env = _safe_child_environment(self.codex_home, self.environment)
            try:
                popen_options: dict[str, Any] = {}
                if os.name == "posix":
                    popen_options["start_new_session"] = True
                proc = subprocess.Popen(
                    # stdio is the app-server default; keeping the command
                    # minimal also works with older supported Codex builds.
                    [self.binary, "app-server"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                    **popen_options,
                )
            except (OSError, ValueError) as exc:
                raise CodexAppError(f"failed to start Codex app-server: {exc}") from exc

            with self._state_lock:
                # close() takes _start_lock too, so it cannot race this
                # assignment; retain the check as a defensive invariant.
                if self._closed:
                    self._shutdown_process(proc)
                    raise CodexAppError("Codex app client was closed during startup")
                self._generation += 1
                generation = self._generation
                self._proc = proc
                self._proc_identity = _capture_process_identity(proc)
                self._reader_threads = [
                    threading.Thread(target=self._read_stdout, args=(proc, generation), daemon=True),
                    threading.Thread(target=self._read_stderr, args=(proc, generation), daemon=True),
                ]
                for thread in self._reader_threads:
                    thread.start()

            try:
                self._request(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "hierarchy",
                            "title": "Hierarchy",
                            "version": "0.1",
                        },
                        # ``runtimeWorkspaceRoots`` is part of Codex's
                        # experimental app-server surface.  The server
                        # rejects thread/start when the client does not
                        # explicitly opt into that capability.
                        "capabilities": {"experimentalApi": True},
                    },
                    timeout=self.timeout,
                )
                self._send({"method": "initialized", "params": {}})
                with self._state_lock:
                    self._initialized = True
            except Exception:
                self._retire()
                raise

    def close(self) -> None:
        """Permanently close this client and terminate its child process."""
        # Serialize against Popen/assignment/initialize. Without this lock a
        # close could observe _proc=None between Popen and assignment, then
        # leave a newly spawned child running after the client is closed.
        with self._start_lock:
            with self._state_lock:
                if self._closed:
                    return
                self._closed = True
                proc = self._proc
        if proc is not None:
            self._shutdown_process(proc)

    def status(self) -> dict[str, Any]:
        """Return non-secret availability/login status for this client config."""
        return codex_status(
            binary=self.binary,
            codex_home=self.codex_home,
            timeout=min(self.timeout, 5.0),
            environment=self.environment,
        )

    def run_turn(
        self,
        thread_id: str | None,
        cwd: str,
        model: str | None,
        instructions: str,
        text: str,
        on_event: EventCallback | None = None,
    ) -> CodexTurnResult:
        """Run one turn, creating or resuming a Codex thread as needed.

        ``thread_id=None`` starts a persistent thread.  A supplied ID is
        resumed after a process restart; IDs already started by this client are
        reused without an unnecessary resume call.
        """
        cwd_value = self._validate_cwd(cwd)
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError("model must be a non-empty string or None")
        if not isinstance(instructions, str):
            raise ValueError("instructions must be a string")

        with self._turn_lock:
            self.start()
            active_thread_id = thread_id
            session_params: dict[str, Any] = {
                "cwd": cwd_value,
                "approvalPolicy": "never",
                "sandbox": "workspace-write",
                "runtimeWorkspaceRoots": [cwd_value],
            }
            if model is not None:
                session_params["model"] = model
            if instructions.strip():
                session_params["baseInstructions"] = instructions

            if active_thread_id is None:
                try:
                    response = self._request("thread/start", session_params, timeout=self.timeout)
                    active_thread_id = self._thread_id_from_response(response)
                except CodexAppError:
                    self._retire()
                    raise
            elif active_thread_id not in self._known_threads:
                try:
                    response = self._request(
                        "thread/resume",
                        {**session_params, "threadId": str(active_thread_id)},
                        timeout=self.timeout,
                    )
                    resumed_id = self._thread_id_from_response(response, fallback=str(active_thread_id))
                    if resumed_id != str(active_thread_id):
                        raise CodexAppError(
                            f"Codex resumed unexpected thread {resumed_id!r}", method="thread/resume"
                        )
                except CodexAppError:
                    self._retire()
                    raise

            active_thread_id = str(active_thread_id)
            self._known_threads.add(active_thread_id)
            try:
                turn_params: dict[str, Any] = {
                    "threadId": active_thread_id,
                    "input": [{"type": "text", "text": text}],
                    "approvalPolicy": "never",
                    "sandboxPolicy": {
                        "type": "workspaceWrite",
                        "writableRoots": [cwd_value],
                        "networkAccess": True,
                    },
                }
                if model is not None:
                    turn_params["model"] = model
                turn_response = self._request("turn/start", turn_params, timeout=self.timeout)
                turn = turn_response.get("turn") if isinstance(turn_response, dict) else None
                turn_id = str((turn or {}).get("id") or "")
                if not turn_id:
                    raise CodexAppError("Codex turn/start returned no turn id", method="turn/start")
            except CodexAppError:
                self._retire()
                raise
            except (AttributeError, TypeError) as exc:
                self._retire()
                raise CodexAppError(
                    "Codex turn/start returned a malformed response", method="turn/start"
                ) from exc
            return self._drive_turn(active_thread_id, turn_id, on_event, self._generation)

    @staticmethod
    def _validate_cwd(cwd: str) -> str:
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError("cwd must be a non-empty absolute path")
        path = Path(cwd).expanduser()
        if not path.is_absolute() or "\x00" in str(path):
            raise ValueError("cwd must be a non-empty absolute path")
        return str(path)

    @staticmethod
    def _thread_id_from_response(response: Any, fallback: str | None = None) -> str:
        thread = response.get("thread") if isinstance(response, dict) else None
        if isinstance(thread, dict):
            value = thread.get("id") or thread.get("sessionId") or thread.get("threadId")
            if value:
                return str(value)
        if isinstance(response, dict):
            for key in ("threadId", "sessionId"):
                if response.get(key):
                    return str(response[key])
        if fallback:
            return fallback
        raise CodexAppError("Codex thread response returned no thread id")

    def _drive_turn(
        self, thread_id: str, turn_id: str, on_event: EventCallback | None, generation: int
    ) -> CodexTurnResult:
        deadline = time.monotonic() + self.timeout
        final_text = ""
        terminal_error = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._interrupt_and_retire(thread_id, turn_id, "turn timed out")
            proc = self._proc_snapshot()
            if proc is None or proc.poll() is not None:
                self._retire()
                raise CodexAppError("Codex app-server process exited during turn")

            self._drain_server_requests(generation)
            try:
                note_generation, note = self._events.get(timeout=min(self._POLL_INTERVAL, remaining))
            except queue.Empty:
                continue
            if note_generation != generation or not self._belongs_to_turn(note, thread_id, turn_id):
                continue
            method = str(note.get("method") or "")
            if on_event is not None and self._is_turn_event(note, method):
                try:
                    on_event(note)
                except Exception:
                    # Progress UI must never break the model turn.
                    pass

            params = note.get("params") or {}
            if not isinstance(params, dict):
                continue
            if method == "item/completed":
                item = params.get("item")
                if isinstance(item, dict) and item.get("type") == "agentMessage":
                    final_text = str(item.get("text") or "")
            elif method == "turn/completed":
                turn = params.get("turn")
                turn = turn if isinstance(turn, dict) else {}
                status = str(turn.get("status") or "completed")
                if terminal_error and status == "completed":
                    status = "failed"
                return CodexTurnResult(final_text, status, thread_id, turn_id)
            elif method == "error" and not bool(params.get("willRetry")):
                # Codex normally follows this notification with
                # turn/completed. Keep draining so the active turn reaches a
                # terminal state and its completion is not left queued for a
                # subsequent request.
                terminal_error = True

    @staticmethod
    def _belongs_to_turn(note: dict[str, Any], thread_id: str, turn_id: str) -> bool:
        params = note.get("params") or {}
        if not isinstance(params, dict):
            return False
        item = params.get("item")
        item = item if isinstance(item, dict) else {}
        turn = params.get("turn")
        turn = turn if isinstance(turn, dict) else {}
        observed_thread = params.get("threadId") or turn.get("threadId") or item.get("threadId")
        observed_turn = params.get("turnId") or turn.get("id") or item.get("turnId")
        method = str(note.get("method") or "")
        if method in {"item/completed", "turn/completed", "error"} and (
            observed_thread is None or observed_turn is None
        ):
            return False
        if observed_thread is not None and str(observed_thread) != thread_id:
            return False
        if observed_turn is not None and str(observed_turn) != turn_id:
            return False
        return True

    @staticmethod
    def _is_turn_event(note: dict[str, Any], method: str) -> bool:
        """Exclude thread-only lifecycle noise from the turn progress hook."""
        params = note.get("params")
        if not isinstance(params, dict):
            return False
        if params.get("turnId") is not None or isinstance(params.get("turn"), dict):
            return True
        return method in {"turn/started", "turn/completed", "error"}

    def _drain_server_requests(self, generation: int) -> None:
        while True:
            try:
                request_generation, request = self._server_requests.get_nowait()
            except queue.Empty:
                return
            if request_generation != generation:
                continue
            self._handle_server_request(request)

    def _handle_server_request(self, request: dict[str, Any]) -> None:
        request_id = request.get("id")
        method = str(request.get("method") or "")
        params = request.get("params") or {}
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            self._send({"id": request_id, "result": {"decision": "decline"}})
        elif method == "mcpServer/elicitation/request":
            self._send(
                {
                    "id": request_id,
                    "result": {"action": "decline", "content": None, "_meta": None},
                }
            )
        else:
            self._send(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unsupported method: {method}"},
                }
            )

    def _request(self, method: str, params: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        with self._request_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            reply_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = reply_queue
        try:
            self._send({"id": request_id, "method": method, "params": params})
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexAppError(
                        f"Codex app-server {method} timed out after {timeout:g}s", method=method
                    )
                try:
                    message = reply_queue.get(timeout=min(self._POLL_INTERVAL, remaining))
                    break
                except queue.Empty:
                    proc = self._proc_snapshot()
                    if proc is None or proc.poll() is not None:
                        raise CodexAppError(
                            f"Codex app-server exited while waiting for {method}", method=method
                        )
            if "error" in message:
                error = message.get("error") or {}
                raise CodexAppError(
                    str(error.get("message") or f"Codex {method} failed"),
                    code=error.get("code"),
                    method=method,
                    data=error.get("data"),
                )
            result = message.get("result")
            return result if isinstance(result, dict) else {}
        finally:
            with self._request_lock:
                self._pending.pop(request_id, None)

    def _send(self, message: dict[str, Any]) -> None:
        proc = self._proc_snapshot()
        if proc is None or proc.poll() is not None:
            raise CodexAppError("Codex app-server process is not running")
        stream = getattr(proc, "stdin", None)
        if stream is None:
            raise CodexAppError("Codex app-server stdin is unavailable")
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._write_lock:
            try:
                try:
                    stream.write(payload)
                except TypeError:
                    stream.write(payload.encode("utf-8"))
                stream.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise CodexAppError(f"failed writing to Codex app-server: {exc}") from exc

    def _proc_snapshot(self) -> Any:
        with self._state_lock:
            return self._proc

    def _read_stdout(self, proc: Any, generation: int) -> None:
        stream = getattr(proc, "stdout", None)
        if stream is None:
            return
        try:
            while True:
                line = stream.readline()
                if line in ("", b""):
                    return
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                try:
                    message = json.loads(str(line))
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(message, dict):
                    continue
                if "id" in message and ("result" in message or "error" in message):
                    with self._request_lock:
                        try:
                            pending = self._pending.get(message["id"])
                        except TypeError:
                            # JSON-RPC ids must be scalar; ignore malformed
                            # future-server output without killing the reader.
                            continue
                    if pending is not None:
                        try:
                            pending.put_nowait(message)
                        except queue.Full:
                            pass
                elif message.get("method"):
                    target = self._server_requests if "id" in message else self._events
                    target.put((generation, message))
        except (OSError, ValueError):
            return

    def _read_stderr(self, proc: Any, generation: int) -> None:
        stream = getattr(proc, "stderr", None)
        if stream is None:
            return
        try:
            while True:
                line = stream.readline()
                if line in ("", b""):
                    return
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                self._stderr.append(str(line).rstrip()[: self._MAX_STDERR_LINE_CHARS])
        except (OSError, ValueError):
            return

    def _interrupt_and_retire(self, thread_id: str, turn_id: str, reason: str) -> None:
        try:
            self._request(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
                timeout=min(self.timeout, 5.0),
            )
        except CodexAppError:
            pass
        self._retire()
        raise CodexAppError(f"Codex {reason}", method="turn")

    def _retire(self) -> None:
        with self._state_lock:
            proc = self._proc
            self._generation += 1
            self._initialized = False
            self._known_threads.clear()
        if proc is not None:
            self._shutdown_process(proc)

    def _shutdown_process(self, proc: Any) -> None:
        with self._state_lock:
            if self._proc is proc:
                self._proc = None
                self._initialized = False
                identity = self._proc_identity
                self._proc_identity = None
            else:
                identity = None
        stream = getattr(proc, "stdin", None)
        try:
            if stream is not None and not getattr(stream, "closed", False):
                stream.close()
        except (OSError, ValueError):
            pass
        if _signal_owned_group(proc, identity, signal.SIGTERM):
            try:
                proc.wait(timeout=min(self.timeout, 2.0))
            except (OSError, subprocess.TimeoutExpired, ValueError):
                if _signal_owned_group(proc, identity, signal.SIGKILL):
                    try:
                        proc.wait(timeout=1.0)
                    except (OSError, subprocess.TimeoutExpired, ValueError):
                        pass
            return
        # Cross-platform fallback, or when POSIX group identity could not be
        # proven. Popen still targets only the exact child object we spawned;
        # never guess a process group or signal an unrelated PID.
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=min(self.timeout, 2.0))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                pass


def _linux_process_starttime(pid: int) -> str | None:
    """Read the kernel start-time field without relying on a guessed target."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None
    closing = stat.rfind(")")
    if closing < 0:
        return None
    fields = stat[closing + 2 :].split()
    # The suffix starts at procfs field 3; starttime is field 22.
    return fields[19] if len(fields) > 19 else None


def _capture_process_identity(proc: Any) -> _ProcessIdentity | None:
    """Bind group cleanup to a verified POSIX session leader we spawned."""
    if os.name != "posix":
        return None
    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int) or pid <= 1 or pid == os.getpid():
        return None
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return None
    # start_new_session=True makes the child its own process-group leader.
    if pgid != pid or pgid == os.getpgrp():
        return None
    return _ProcessIdentity(pid=pid, pgid=pgid, starttime=_linux_process_starttime(pid))


def _signal_owned_group(
    proc: Any, identity: _ProcessIdentity | None, sig: signal.Signals
) -> bool:
    """Signal only the still-owned, still-leader process group."""
    if os.name != "posix" or identity is None:
        return False
    if getattr(proc, "pid", None) != identity.pid or proc.poll() is not None:
        return False
    try:
        if os.getpgid(identity.pid) != identity.pgid or identity.pgid != identity.pid:
            return False
        if identity.starttime is not None and _linux_process_starttime(identity.pid) != identity.starttime:
            return False
        if identity.pgid == os.getpgrp() or identity.pgid == os.getpid():
            return False
        os.killpg(identity.pgid, sig)
        return True
    except OSError:
        return False
