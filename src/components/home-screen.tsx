import { Plus, Search } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { IconButton, Screen } from "@/components/chrome";
import type { Bot, Group } from "@/lib/types";
import { previewOf, timeLabel } from "@/lib/utils";

export function HomeScreen({
  bots,
  groups,
  hidden,
  pinned,
  onOpenBot,
  onOpenGroup,
  onSearch,
  onNew,
  onSettings,
  onComputer,
}: {
  bots: Bot[];
  groups: Group[];
  hidden: string[];
  pinned: string[];
  onOpenBot: (id: string) => void;
  onOpenGroup: (id: string) => void;
  onSearch: () => void;
  onNew: () => void;
  onSettings: () => void;
  onComputer: () => void;
}) {
  const visibleBots = bots.filter((b) => !hidden.includes(b.id));
  const spotlight = visibleBots.slice(0, 3);
  const botRows = [...visibleBots].sort((a, b) => {
    const ap = pinned.includes(a.id) ? 0 : 1;
    const bp = pinned.includes(b.id) ? 0 : 1;
    return ap - bp;
  });

  return (
    <Screen>
      <header className="flex items-center gap-2 px-3 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <button
          type="button"
          onClick={onSettings}
          className="grid size-11 place-items-center overflow-hidden rounded-full bg-elevated text-[13px] font-semibold"
          aria-label="Settings"
        >
          H
        </button>
        <div className="flex-1" />
        <IconButton label="Search" onClick={onSearch}>
          <Search className="size-5" strokeWidth={1.75} />
        </IconButton>
        <IconButton label="New" onClick={onNew}>
          <Plus className="size-6" strokeWidth={1.75} />
        </IconButton>
      </header>

      {spotlight.length > 0 ? (
        <div className="flex gap-5 overflow-x-auto px-5 pb-4 pt-1">
          {spotlight.map((bot) => (
            <button
              key={bot.id}
              type="button"
              onClick={() => onOpenBot(bot.id)}
              className="flex w-20 shrink-0 flex-col items-center gap-2"
            >
              <BotAvatar name={bot.name} size="lg" />
              <span className="w-full truncate text-center text-[12px] font-medium text-fg">{bot.name}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex-1">
        {groups.map((g) => (
          <button
            key={g.id}
            type="button"
            onClick={() => onOpenGroup(g.id)}
            className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-elevated/60"
          >
            <div className="relative size-12">
              {g.memberIds.slice(0, 2).map((id, i) => {
                const bot = bots.find((b) => b.id === id);
                return (
                  <div key={id} className={i === 0 ? "absolute left-0 top-0" : "absolute bottom-0 right-0"}>
                    <BotAvatar name={bot?.name || "Group"} size="sm" stacked />
                  </div>
                );
              })}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[15px] font-semibold">{g.name}</span>
                <span className="shrink-0 text-[12px] text-subtle">{timeLabel(g.updatedAt)}</span>
              </div>
              <p className="truncate text-[13px] text-muted">{previewOf(g.preview || "Group chat")}</p>
            </div>
          </button>
        ))}

        {botRows.map((bot) => (
          <button
            key={bot.id}
            type="button"
            onClick={() => onOpenBot(bot.id)}
            className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-elevated/60"
          >
            <BotAvatar name={bot.name} />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[15px] font-semibold">{bot.name}</span>
                <span className="shrink-0 text-[12px] text-subtle">
                  {bot.status === "working" ? "Now" : ""}
                </span>
              </div>
              <p className="truncate text-[13px] text-muted">
                {previewOf(bot.preview || bot.job)}
              </p>
            </div>
            {bot.status === "working" ? (
              <span className="size-2 shrink-0 rounded-full bg-ok" />
            ) : null}
          </button>
        ))}

        {bots.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <p className="text-[15px] font-semibold">No bots yet</p>
            <p className="mt-1 text-[13px] text-muted">Create an agent or kick off a project to seed the floor.</p>
          </div>
        ) : null}
      </div>

      <button
        type="button"
        onClick={onComputer}
        className="mx-4 mb-[max(1rem,env(safe-area-inset-bottom))] mt-2 rounded-[18px] border border-line bg-surface px-4 py-3 text-left"
      >
        <div className="text-[13px] font-semibold">Shell</div>
        <div className="text-[12px] text-muted">Run commands on the VPS</div>
      </button>
    </Screen>
  );
}
