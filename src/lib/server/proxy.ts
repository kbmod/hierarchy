import { createServerFn } from "@tanstack/react-start";

export type ProxyInput = {
  baseUrl: string;
  token?: string;
  method: "GET" | "POST";
  path: string;
  body?: string;
  timeoutMs?: number;
};

export type ProxyResult = {
  ok: boolean;
  status: number;
  json: string;
  error: string;
};

// Keep the preview-only demo away from 8765, which is reserved for the real
// hierarchy.service and must be able to bind on every VPS interface.
const DEMO_PORT = "18765";
const DEMO = `http://127.0.0.1:${DEMO_PORT}`;

function isLoopbackHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return host === "localhost" || /^127(?:\.\d{1,3}){3}$/.test(host);
}

function resolveBase(raw: string): URL {
  const value = raw.trim() === "demo" || raw.trim() === "" ? DEMO : raw.trim();
  const url = new URL(value);
  const host = url.hostname.toLowerCase();
  // Remote VPS calls never come through this server function; the browser or
  // Capacitor calls them directly. Keeping this allowlist demo-only prevents
  // the public function from becoming an SSRF path into the host.
  if (url.protocol !== "http:" || !isLoopbackHost(host) || url.port !== DEMO_PORT) {
    throw new Error(`Local demo agent only on port ${DEMO_PORT}`);
  }
  url.hostname = "127.0.0.1";
  return url;
}

export const proxyVps = createServerFn({ method: "POST" })
  .validator((input: ProxyInput) => input)
  .handler(async ({ data }): Promise<ProxyResult> => {
    let target: URL;
    try {
      target = resolveBase(data.baseUrl);
    } catch (err) {
      return {
        ok: false,
        status: 400,
        json: "{}",
        error: err instanceof Error ? err.message : "Invalid agent URL",
      };
    }
    const path = data.path.startsWith("/") ? data.path : `/${data.path}`;
    if (path.startsWith("//") || path.includes("\\")) {
      return { ok: false, status: 400, json: "{}", error: "Agent path must stay on the selected host" };
    }
    const url = new URL(path, target);
    if (url.origin !== target.origin) {
      return { ok: false, status: 400, json: "{}", error: "Agent path must stay on the selected host" };
    }
    const headers: Record<string, string> = { Accept: "application/json" };
    if (data.body !== undefined) headers["Content-Type"] = "application/json";
    const token = data.token?.trim();
    if (token) headers.Authorization = `Bearer ${token}`;

    const timeoutMs = Math.min(Math.max(data.timeoutMs ?? 90_000, 3_000), 120_000);
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        method: data.method,
        headers,
        body: data.method === "POST" ? (data.body ?? "{}") : undefined,
        signal: ac.signal,
      });
      const text = await res.text();
      if (!res.ok) {
        let error = `Agent error ${res.status}`;
        try {
          const parsed = JSON.parse(text) as { error?: string };
          if (parsed?.error) error = parsed.error;
        } catch {
          /* keep */
        }
        return { ok: false, status: res.status, json: text || "{}", error };
      }
      return { ok: true, status: res.status, json: text || "{}", error: "" };
    } catch (err) {
      const message =
        err instanceof Error && err.name === "AbortError"
          ? "Agent timed out"
          : err instanceof Error
            ? err.message
            : "Agent unreachable";
      return { ok: false, status: 0, json: "{}", error: message };
    } finally {
      clearTimeout(timer);
    }
  });
