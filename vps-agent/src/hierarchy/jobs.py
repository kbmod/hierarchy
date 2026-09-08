"""Background jobs so bots keep working after the phone leaves."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

JobFn = Callable[[], str]


class JobBoard:
    def __init__(self, workers: int = 4) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._closed = False
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bot")

    def submit(self, *, bot_id: str, kind: str, fn: JobFn) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:16]
        row: dict[str, Any] = {
            "id": job_id,
            "bot_id": bot_id,
            "kind": kind,
            "status": "working",
            "text": "",
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            if self._closed:
                raise RuntimeError("job board is closed")
            self._jobs[job_id] = row
            try:
                # Keep submission under the same lock as the closed check so
                # shutdown cannot race between accepting the row and handing
                # it to the executor.
                self._pool.submit(self._run, job_id, fn)
            except RuntimeError:
                self._jobs.pop(job_id, None)
                raise RuntimeError("job board is closed") from None
        return dict(row)

    def close(self, wait: bool = True) -> None:
        """Stop accepting jobs and drain or cancel the executor."""
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=wait, cancel_futures=not wait)

    def _run(self, job_id: str, fn: JobFn) -> None:
        try:
            text = fn() or ""
            self._update(job_id, status="done", text=text, error=None)
        except Exception as exc:  # noqa: BLE001
            self._update(job_id, status="error", text="", error=str(exc))

    def _update(self, job_id: str, **patch: Any) -> None:
        with self._lock:
            row = self._jobs.get(job_id)
            if not row:
                return
            row.update(patch)
            row["updated_at"] = time.time()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._jobs.get(job_id)
            return dict(row) if row else None

    def list(self, bot_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(v) for v in self._jobs.values()]
        if bot_id:
            rows = [r for r in rows if r.get("bot_id") == bot_id]
        rows.sort(key=lambda r: float(r.get("updated_at") or 0), reverse=True)
        return rows[:50]
