import type { AuthStatus, Bot, HistoryItem, Job, Project, Routine, ShellState } from "./types";
import { isNativeApp } from "./native";

export class VpsError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.status = status;
  }
}

type Conn = { url: string; token: string };

export function normalizeAgentUrl(raw: string): string {
  let value = raw.trim();
  if (!value || value === "demo") return value;
  if (!/^https?:\/\//i.test(value)) value = `http://${value}`;
  return value.replace(/\/+$/, "");
}

function isLocalDemo(url: string): boolean {
  const value = url.trim().toLowerCase();
  if (!value || value === "demo") return true;
  try {
    const parsed = new URL(normalizeAgentUrl(value));
    return parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  } catch {
    return false;
  }
}

async function directCall<T>(conn: Conn, method: "GET" | "POST", path: string, body?: unknown, timeoutMs = 90_000): Promise<T> {
  const raw = conn.url.trim();
  if (!raw || raw === "demo") {
    throw new VpsError("Set a VPS agent URL in Settings → Agent backends.");
  }
  const base = normalizeAgentUrl(raw);
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = conn.token.trim();
  if (token) headers.Authorization = `Bearer ${token}`;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method,
      headers,
      body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
      signal: ac.signal,
    });
    const text = await res.text();
    let parsed: unknown = {};
    try {
      parsed = text ? JSON.parse(text) : {};
    } catch {
      throw new VpsError("Agent returned invalid JSON", res.status);
    }
    if (!res.ok) {
      const err = parsed as { error?: string };
      throw new VpsError(err.error || `Agent error ${res.status}`, res.status);
    }
    return parsed as T;
  } catch (err) {
    if (err instanceof VpsError) throw err;
    if (err instanceof Error && err.name === "AbortError") throw new VpsError("Agent timed out");
    throw new VpsError(err instanceof Error ? err.message : "Agent unreachable");
  } finally {
    clearTimeout(timer);
  }
}

async function proxyCall<T>(conn: Conn, method: "GET" | "POST", path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  if (import.meta.env.VITE_APK === "1") {
    throw new VpsError("Set a VPS agent URL in Settings → Agent backends.");
  }
  const { proxyVps } = await import("./server/proxy");
  const result = await proxyVps({
    data: {
      baseUrl: conn.url || "demo",
      token: conn.token,
      method,
      path,
      body: body === undefined ? undefined : JSON.stringify(body),
      timeoutMs,
    },
  });
  if (!result.ok) throw new VpsError(result.error, result.status);
  try {
    return JSON.parse(result.json) as T;
  } catch {
    throw new VpsError("Agent returned invalid JSON", result.status);
  }
}

async function nativeHttpCall<T>(
  conn: Conn,
  method: "GET" | "POST",
  path: string,
  body?: unknown,
  timeoutMs = 90_000,
): Promise<T> {
  const raw = conn.url.trim();
  if (!raw || raw === "demo") {
    throw new VpsError("Set a VPS agent URL in Settings → Agent backends.");
  }
  const base = normalizeAgentUrl(raw);
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = conn.token.trim();
  if (token) headers.Authorization = `Bearer ${token}`;

  const { CapacitorHttp } = await import("@capacitor/core");
  let result: { status: number; data: unknown };
  try {
    result = await CapacitorHttp.request({
      url,
      method,
      headers,
      data: method === "POST" ? (body ?? {}) : undefined,
      connectTimeout: timeoutMs,
      readTimeout: timeoutMs,
      responseType: "json",
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new VpsError(
      `${message} (native GET/POST ${url}). If this is Tailscale, confirm the Tailscale VPN is on and hierarchy.service is listening on 0.0.0.0:8765.`,
    );
  }
  const parsed =
    typeof result.data === "string"
      ? (() => {
          try {
            return JSON.parse(result.data || "{}") as unknown;
          } catch {
            throw new VpsError(`Agent returned non-JSON (${result.status}) from ${url}`);
          }
        })()
      : (result.data ?? {});
  if (result.status < 200 || result.status >= 300) {
    const err = parsed as { error?: string };
    throw new VpsError(err.error || `Agent error ${result.status} from ${url}`, result.status);
  }
  return parsed as T;
}

async function call<T>(conn: Conn, method: "GET" | "POST", path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  if (import.meta.env.VITE_APK === "1" || isNativeApp()) {
    return nativeHttpCall<T>(conn, method, path, body, timeoutMs);
  }
  if (!isLocalDemo(conn.url)) {
    return directCall<T>(conn, method, path, body, timeoutMs);
  }
  return proxyCall<T>(conn, method, path, body, timeoutMs);
}

export const vps = {
  health: (c: Conn, timeoutMs = 20_000) =>
    call<{ ok: boolean; auth?: boolean; bots?: number; computer?: boolean }>(c, "GET", "/api/health", undefined, timeoutMs),
  auth: (c: Conn) => call<AuthStatus>(c, "GET", "/api/auth"),
  bots: (c: Conn) => call<{ bots: Bot[] }>(c, "GET", "/api/bots"),
  history: (c: Conn, id: string) => call<{ history: HistoryItem[] }>(c, "GET", `/api/bots/${id}/history`),
  computer: (c: Conn) => call<ShellState>(c, "GET", "/api/computer"),
  projects: (c: Conn) => call<{ projects: Project[] }>(c, "GET", "/api/projects"),
  routines: (c: Conn, id: string) => call<{ routines: Routine[] }>(c, "GET", `/api/bots/${id}/routines`),
  job: (c: Conn, id: string) => call<Job>(c, "GET", `/api/jobs/${id}`),
  jobs: (c: Conn, botId?: string) =>
    call<{ jobs: Job[] }>(c, "GET", botId ? `/api/jobs?bot=${encodeURIComponent(botId)}` : "/api/jobs"),
  files: (c: Conn, path = ".") => call<{ path: string; listing: string }>(c, "GET", `/api/computer/files?path=${encodeURIComponent(path)}`),
  setKey: (c: Conn, provider: string, api_key: string, model?: string) =>
    call<AuthStatus>(c, "POST", "/api/auth/key", { provider, api_key, model }),
  useProvider: (c: Conn, provider: string) => call<AuthStatus>(c, "POST", "/api/auth/use", { provider }),
  oauthStart: (c: Conn, provider: "grok" | "chatgpt") =>
    call<{ session: string; provider: string; user_code: string; verification_uri: string }>(
      c,
      "POST",
      "/api/auth/oauth/start",
      { provider },
    ),
  oauthPoll: (c: Conn, session: string) =>
    call<{ ok: boolean; pending?: boolean } & Partial<AuthStatus>>(c, "POST", "/api/auth/oauth/poll", { session }),
  floor: (c: Conn) => call<{ bots: Bot[] }>(c, "POST", "/api/floor", {}),
  createBot: (
    c: Conn,
    input: {
      name: string;
      job: string;
      description: string;
      reports_to?: string;
      provider?: string;
      model?: string;
      vpsId?: string;
    },
  ) =>
    call<{
      id: string;
      name: string;
      job: string;
      reports_to?: string | null;
      provider?: string | null;
      model?: string | null;
    }>(c, "POST", "/api/bots", input),
  updateBot: (
    c: Conn,
    id: string,
    input: { provider?: string; model?: string; job?: string; description?: string },
  ) =>
    call<{
      id: string;
      name: string;
      job: string;
      provider?: string | null;
      model?: string | null;
    }>(c, "POST", `/api/bots/${id}`, input),
  chat: (c: Conn, id: string, text: string) =>
    call<{ bot_id: string; text: string; job_id?: string; status?: string }>(
      c,
      "POST",
      `/api/bots/${id}/chat`,
      { text, async: true },
      20_000,
    ),
  dm: (c: Conn, toId: string, senderId: string, text: string) =>
    call<{ bot_id: string; text: string }>(c, "POST", `/api/bots/${toId}/dm`, { sender_id: senderId, text }, 110_000),
  kickoff: (c: Conn, input: { name: string; outcome: string; lead_id?: string }) =>
    call<{
      project: Project;
      lead: { bot_id: string; text: string };
      specialist: { bot_id: string; text: string } | null;
    }>(c, "POST", "/api/projects", input, 110_000),
  saveRoutine: (c: Conn, botId: string, payload: Partial<Routine> & { title?: string }) =>
    call<{ routines: Routine[] }>(c, "POST", `/api/bots/${botId}/routines`, payload),
  runRoutine: (c: Conn, botId: string, id: string) =>
    call<{ job_id: string; routines: Routine[] }>(c, "POST", `/api/bots/${botId}/routines/run`, { id }),
  exec: (c: Conn, cmd: string) =>
    call<{ ok: boolean; output: string } & ShellState>(c, "POST", "/api/computer/exec", { cmd }, 90_000),
};
