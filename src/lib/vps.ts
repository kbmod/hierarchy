import type { AuthStatus, Bot, ComputerScreen, HistoryItem, Project, Routine } from "./types";
import { proxyVps } from "./server/proxy";

export class VpsError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.status = status;
  }
}

type Conn = { url: string; token: string };

async function call<T>(conn: Conn, method: "GET" | "POST", path: string, body?: unknown, timeoutMs?: number): Promise<T> {
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

export const vps = {
  health: (c: Conn) => call<{ ok: boolean; auth?: boolean; bots?: number }>(c, "GET", "/api/health", undefined, 8000),
  auth: (c: Conn) => call<AuthStatus>(c, "GET", "/api/auth"),
  bots: (c: Conn) => call<{ bots: Bot[] }>(c, "GET", "/api/bots"),
  history: (c: Conn, id: string) => call<{ history: HistoryItem[] }>(c, "GET", `/api/bots/${id}/history`),
  computer: (c: Conn) => call<{ screens: ComputerScreen[] }>(c, "GET", "/api/computer"),
  botComputer: (c: Conn, id: string) => call<ComputerScreen>(c, "GET", `/api/bots/${id}/computer`),
  projects: (c: Conn) => call<{ projects: Project[] }>(c, "GET", "/api/projects"),
  routines: (c: Conn, id: string) => call<{ routines: Routine[] }>(c, "GET", `/api/bots/${id}/routines`),
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
  createBot: (c: Conn, input: { name: string; job: string; description: string; reports_to?: string }) =>
    call<{ id: string; name: string; job: string; reports_to?: string | null }>(c, "POST", "/api/bots", input),
  chat: (c: Conn, id: string, text: string) =>
    call<{ bot_id: string; text: string }>(c, "POST", `/api/bots/${id}/chat`, { text }, 110_000),
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
};
