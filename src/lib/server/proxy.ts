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

const DEMO = "http://127.0.0.1:8765";
const BLOCKED = new Set(["169.254.169.254", "metadata.google.internal", "metadata.internal"]);

function resolveBase(raw: string): URL {
  const value = raw.trim() === "demo" || raw.trim() === "" ? DEMO : raw.trim();
  const url = new URL(value);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Agent URL must be http or https");
  }
  const host = url.hostname.toLowerCase();
  if (BLOCKED.has(host)) throw new Error("Blocked host");
  if (host === "localhost") url.hostname = "127.0.0.1";
  if ((host === "127.0.0.1" || host === "localhost") && (url.port || "80") !== "8765") {
    throw new Error("Local agent only on port 8765");
  }
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
    const url = new URL(path, target);
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
