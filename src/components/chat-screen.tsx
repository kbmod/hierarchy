import { useEffect, useRef, useState } from "react";
import { Mic, Monitor, MoreHorizontal, Plus, SendHorizontal } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { IconButton, Screen, TopBar } from "@/components/chrome";
import type { Bot, HistoryItem } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ChatScreen({
  bot,
  history,
  draft,
  busy,
  error,
  onBack,
  onDraft,
  onSend,
  onComputer,
  onProfile,
  onAttach,
}: {
  bot: Bot;
  history: HistoryItem[];
  draft: string;
  busy: boolean;
  error: string | null;
  onBack: () => void;
  onDraft: (value: string) => void;
  onSend: () => void;
  onComputer: () => void;
  onProfile: () => void;
  onAttach: () => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const [listening, setListening] = useState(false);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [history, busy]);

  function dictate() {
    const Speech = (window as unknown as { webkitSpeechRecognition?: new () => SpeechRec }).webkitSpeechRecognition;
    if (!Speech) {
      onDraft(draft ? draft : "");
      return;
    }
    const rec = new Speech();
    rec.lang = "en-US";
    rec.onresult = (ev: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => {
      const said = ev.results[0]?.[0]?.transcript || "";
      onDraft(draft ? `${draft} ${said}` : said);
      setListening(false);
    };
    rec.onend = () => setListening(false);
    setListening(true);
    rec.start();
  }

  return (
    <Screen>
      <TopBar
        onBack={onBack}
        title={bot.name}
        subtitle={busy ? "Working…" : [bot.provider, bot.model, bot.job].filter(Boolean).join(" · ")}
        right={
          <>
            <IconButton label="Shell" onClick={onComputer}>
              <Monitor className="size-5" strokeWidth={1.75} />
            </IconButton>
            <IconButton label="Bot profile" onClick={onProfile}>
              <MoreHorizontal className="size-5" strokeWidth={1.75} />
            </IconButton>
          </>
        }
      />

      <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-3 py-4">
        {history.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <BotAvatar name={bot.name} size="xl" />
            <div>
              <div className="text-[17px] font-semibold">{bot.name}</div>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">{bot.description}</p>
            </div>
          </div>
        ) : null}

        {history.map((item, i) => {
          const mine = item.role === "user";
          return (
            <div key={`${i}-${item.role}`} className={cn("flex", mine ? "justify-end" : "justify-start")}>
              {!mine ? (
                <div className="mr-2 mt-1">
                  <BotAvatar name={bot.name} size="sm" />
                </div>
              ) : null}
              <div
                className={cn(
                  "max-w-[82%] whitespace-pre-wrap rounded-[22px] px-3.5 py-2.5 text-[15px] leading-snug",
                  mine ? "rounded-br-md bg-user text-user-fg" : "rounded-bl-md bg-bubble text-fg",
                )}
              >
                {item.content}
              </div>
            </div>
          );
        })}

        {busy ? (
          <div className="flex items-center gap-2 pl-1 text-[13px] text-muted">
            <BotAvatar name={bot.name} size="sm" />
            <span className="shimmer rounded-full px-3 py-1">{bot.name} is working</span>
          </div>
        ) : null}

        {error ? <p className="px-2 text-[13px] text-danger">{error}</p> : null}
      </div>

      <form
        className="flex items-end gap-2 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) onSend();
        }}
      >
        <button
          type="button"
          onClick={onAttach}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-elevated"
          aria-label="Attach"
        >
          <Plus className="size-5" strokeWidth={1.75} />
        </button>
        <div className="flex min-h-11 flex-1 items-end rounded-full bg-elevated px-1">
          <textarea
            value={draft}
            onChange={(e) => onDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (draft.trim()) onSend();
              }
            }}
            rows={1}
            placeholder={`Message ${bot.name}`}
            className="max-h-32 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] outline-none placeholder:text-subtle"
          />
          {draft.trim() ? (
            <button
              type="submit"
              className="mb-1 mr-1 grid size-9 place-items-center rounded-full bg-user text-user-fg"
              aria-label="Send"
            >
              <SendHorizontal className="size-4" />
            </button>
          ) : (
            <button
              type="button"
              onClick={dictate}
              className={cn("mb-1 mr-1 grid size-9 place-items-center rounded-full", listening && "bg-user text-user-fg")}
              aria-label="Dictate"
            >
              <Mic className="size-4" />
            </button>
          )}
        </div>
      </form>
    </Screen>
  );
}

type SpeechRec = {
  lang: string;
  start: () => void;
  onresult: ((ev: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void) | null;
  onend: (() => void) | null;
};
