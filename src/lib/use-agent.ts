import { useCallback, useMemo } from "react";
import { useApp } from "./store";
import type { VpsSlot } from "./types";
import { vps, VpsError } from "./vps";

export type Conn = { url: string; token: string };

export function slotConn(slot: VpsSlot | undefined): Conn {
  return { url: slot?.url?.trim() || "", token: slot?.token || "" };
}

export function useConn() {
  const vpsList = useApp((s) => s.vps);
  const activeVpsId = useApp((s) => s.activeVpsId);
  return useMemo(() => {
    const slot = vpsList.find((v) => v.id === activeVpsId) ?? vpsList[0];
    return slotConn(slot);
  }, [vpsList, activeVpsId]);
}

export function useAgent() {
  const conn = useConn();
  const vpsList = useApp((s) => s.vps);
  const activeVpsId = useApp((s) => s.activeVpsId);
  const setBusy = useApp((s) => s.setBusy);
  const setError = useApp((s) => s.setError);

  const connFor = useCallback(
    (vpsId?: string | null): Conn => {
      const slot =
        vpsList.find((v) => v.id === vpsId) ?? vpsList.find((v) => v.id === activeVpsId) ?? vpsList[0];
      return slotConn(slot);
    },
    [vpsList, activeVpsId],
  );

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

  return { conn, connFor, run, vps, setError, setBusy };
}
