import { BotAvatar } from "@/components/bot-avatar";
import { Screen, TopBar } from "@/components/chrome";
import type { ComputerScreen as ScreenData, Routine } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ComputerScreenView({
  screens,
  selectedId,
  routines,
  onBack,
  onSelect,
  onToggleRoutine,
}: {
  screens: ScreenData[];
  selectedId?: string;
  routines: Routine[];
  onBack: () => void;
  onSelect: (id: string) => void;
  onToggleRoutine: (id: string, active: boolean) => void;
}) {
  const current = screens.find((s) => s.id === selectedId) ?? screens[0];
  return (
    <Screen>
      <TopBar onBack={onBack} title="Agent computer" subtitle={current ? `${current.name}'s screen` : "Shared"} />
      <div className="flex gap-2 overflow-x-auto px-4 py-3">
        {screens.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            className={cn(
              "flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px]",
              s.id === current?.id ? "border-fg bg-fg text-bg" : "border-line bg-surface text-fg",
            )}
          >
            <BotAvatar name={s.name} size="sm" />
            {s.name}
          </button>
        ))}
      </div>

      <div className="px-4">
        <div className="overflow-hidden rounded-[24px] border border-line bg-[#111] text-[#e8eaed] shadow-sm">
          <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2 text-[11px]">
            <span className="size-2 rounded-full bg-[#ff5f57]" />
            <span className="size-2 rounded-full bg-[#febc2e]" />
            <span className="size-2 rounded-full bg-[#28c840]" />
            <span className="ml-2 truncate text-white/60">{current?.title || "Desktop"}</span>
            <span className="ml-auto uppercase tracking-wider text-white/40">
              {current?.status === "working" ? "live" : "idle"}
            </span>
          </div>
          <pre className="min-h-56 overflow-auto p-4 font-mono text-[12px] leading-relaxed">
            {(current?.lines?.length ? current.lines : ["$ waiting for work", "# shared /workspace"]).join("\n")}
          </pre>
        </div>
        <p className="mt-2 px-1 text-[12px] text-muted">
          Take over for passwords, 2FA, or CAPTCHA on the VPS desktop, then return control. Every bot shares this
          computer.
        </p>
      </div>

      <div className="mt-6 px-4 pb-8">
        <h2 className="mb-2 text-[13px] font-semibold">Routines</h2>
        {routines.length === 0 ? (
          <p className="text-[13px] text-muted">No routines on this bot yet.</p>
        ) : (
          <ul className="space-y-2">
            {routines.map((r) => (
              <li key={r.id} className="flex items-center justify-between rounded-[18px] bg-surface px-3 py-3">
                <div>
                  <div className="text-[14px] font-medium">{r.title}</div>
                  <div className="text-[12px] text-muted">{r.schedule}</div>
                </div>
                <button
                  type="button"
                  onClick={() => onToggleRoutine(r.id, !r.active)}
                  className={cn(
                    "rounded-full px-3 py-1 text-[12px] font-medium",
                    r.active ? "bg-ok/15 text-ok" : "bg-elevated text-muted",
                  )}
                >
                  {r.active ? "Active" : "Paused"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Screen>
  );
}
