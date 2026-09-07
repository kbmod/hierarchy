import { useEffect, useRef, useState } from "react";
import { Screen, TextField, TopBar } from "@/components/chrome";
import type { ShellState } from "@/lib/types";

export function ShellScreen({
  shell,
  busy,
  onBack,
  onExec,
}: {
  shell: ShellState | null;
  busy: boolean;
  onBack: () => void;
  onExec: (cmd: string) => void;
}) {
  const [cmd, setCmd] = useState("");
  const log = useRef<HTMLPreElement>(null);
  const lines = shell?.lines?.length ? shell.lines : ["$  # VPS shell — no desktop required"];

  useEffect(() => {
    const el = log.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <Screen>
      <TopBar onBack={onBack} title="Shell" subtitle={shell?.cwd || "VPS"} />
      <div className="flex min-h-0 flex-1 flex-col px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3">
        <pre
          ref={log}
          className="min-h-0 flex-1 overflow-auto rounded-[18px] bg-elevated p-3 font-mono text-[12px] leading-relaxed text-fg"
        >
          {lines.join("\n")}
        </pre>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!cmd.trim()) return;
            onExec(cmd.trim());
            setCmd("");
          }}
        >
          <TextField
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            placeholder="Command"
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="off"
            spellCheck={false}
            className="h-11 font-mono text-[13px]"
          />
          <button
            type="submit"
            disabled={busy || !cmd.trim()}
            className="h-11 shrink-0 rounded-[16px] bg-accent px-4 text-[13px] font-semibold text-accent-fg disabled:opacity-40"
          >
            Run
          </button>
        </form>
      </div>
    </Screen>
  );
}
