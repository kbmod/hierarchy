import { useCallback, useMemo } from "react";
import { useApp } from "./store";
import { vps, VpsError } from "./vps";

export function useConn() {
  const vpsList = useApp((s) => s.vps);
  const activeVpsId = useApp((s) => s.activeVpsId);
  return useMemo(() => {
    const slot = vpsList.find((v) => v.id === activeVpsId) ?? vpsList[0];
    return { url: slot?.url || "demo", token: slot?.token || "" };
  }, [vpsList, activeVpsId]);
}

export function useAgent() {
  const conn = useConn();
  const setBusy = useApp((s) => s.setBusy);
  const setError = useApp((s) => s.setError);

  const run = useCallback(
    async <T,>(fn: () => Promise<T>, { quiet = false } = {}): Promise<T | null> => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        return await fn();
      } catch (err) {
        const message = err instanceof VpsError ? err.message : err instanceof Error ? err.message : "Request failed";
        setError(message);
        return null;
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [setBusy, setError],
  );

  return { conn, run, vps, setError, setBusy };
}
