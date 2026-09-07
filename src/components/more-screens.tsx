import { useEffect, useState } from "react";
import { SendHorizontal } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import {
  AreaField,
  Banner,
  Field,
  GhostButton,
  PrimaryButton,
  Screen,
  TextField,
  TopBar,
} from "@/components/chrome";
import type { AuthStatus, Bot, Group } from "@/lib/types";
import { useApp, type AppearanceMode } from "@/lib/store";
import { cn } from "@/lib/utils";

export function SettingsScreen({
  auth,
  onBack,
  onOpen,
}: {
  auth: AuthStatus | null;
  onBack: () => void;
  onOpen: (name: "backends" | "providers" | "install" | "project") => void;
}) {
  const appearance = useApp((s) => s.appearance);
  const setAppearance = useApp((s) => s.setAppearance);
  const active = useApp((s) => s.activeVps());
  return (
    <Screen>
      <TopBar onBack={onBack} title="Settings" />
      <div className="space-y-6 px-4 py-4 pb-10">
        <section>
          <h2 className="mb-2 text-[12px] font-medium uppercase tracking-[0.12em] text-muted">Account</h2>
          <Row label="Agent backend" value={active.label} onClick={() => onOpen("backends")} />
          <Row
            label="Providers"
            value={auth?.active ? String(auth.active) : "stub"}
            onClick={() => onOpen("providers")}
          />
          <Row label="Install on this phone" value="Android" onClick={() => onOpen("install")} />
        </section>
        <section>
          <h2 className="mb-2 text-[12px] font-medium uppercase tracking-[0.12em] text-muted">Appearance</h2>
          <div className="flex gap-2">
            {(["system", "light", "dark"] as AppearanceMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setAppearance(mode)}
                className={cn(
                  "h-10 flex-1 rounded-full text-[13px] font-medium capitalize",
                  appearance === mode ? "bg-fg text-bg" : "bg-elevated text-fg",
                )}
              >
                {mode}
              </button>
            ))}
          </div>
        </section>
        <section>
          <h2 className="mb-2 text-[12px] font-medium uppercase tracking-[0.12em] text-muted">Work</h2>
          <Row label="Kick off a project" value="Assign the floor" onClick={() => onOpen("project")} />
        </section>
      </div>
    </Screen>
  );
}

function Row({ label, value, onClick }: { label: string; value: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between border-b border-line py-3.5 text-left"
    >
      <span className="text-[15px]">{label}</span>
      <span className="text-[13px] text-muted">{value}</span>
    </button>
  );
}

export function BackendsScreen({
  healthNote,
  onBack,
  onTest,
}: {
  healthNote: string | null;
  onBack: () => void;
  onTest: (id: string) => void;
}) {
  const slots = useApp((s) => s.vps);
  const activeVpsId = useApp((s) => s.activeVpsId);
  const upsert = useApp((s) => s.upsertVps);
  const setActive = useApp((s) => s.setActiveVps);
  return (
    <Screen>
      <TopBar onBack={onBack} title="Agent backends" subtitle="Two VPS slots" />
      <div className="space-y-4 px-4 py-4">
        {slots.map((slot) => (
          <div key={slot.id} className="rounded-[24px] border border-line bg-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[13px] font-semibold capitalize">{slot.role}</span>
              <button
                type="button"
                onClick={() => setActive(slot.id)}
                className={cn(
                  "rounded-full px-3 py-1 text-[12px] font-medium",
                  activeVpsId === slot.id ? "bg-fg text-bg" : "bg-elevated text-muted",
                )}
              >
                {activeVpsId === slot.id ? "Active" : "Use"}
              </button>
            </div>
            <div className="space-y-3">
              <Field label="Label">
                <TextField value={slot.label} onChange={(e) => upsert({ ...slot, label: e.target.value })} />
              </Field>
              <Field label="Agent URL">
                <TextField
                  value={slot.url}
                  placeholder="https://your-vps:8765"
                  onChange={(e) => upsert({ ...slot, url: e.target.value })}
                  autoCapitalize="none"
                />
              </Field>
              <Field label="Token">
                <TextField
                  type="password"
                  value={slot.token}
                  onChange={(e) => upsert({ ...slot, token: e.target.value })}
                />
              </Field>
              <GhostButton onClick={() => onTest(slot.id)}>Test connection</GhostButton>
            </div>
          </div>
        ))}
        {healthNote ? <Banner>{healthNote}</Banner> : null}
        <a
          href="/hierarchy-agent.tgz"
          download="hierarchy-agent.tgz"
          className="flex h-12 w-full items-center justify-center rounded-[20px] border border-line bg-surface px-4 text-[15px] font-medium text-fg"
        >
          Download VPS agent
        </a>
        <div className="rounded-[20px] bg-elevated p-4 text-[13px] leading-relaxed text-muted">
          On each VPS, unpack the agent, then run
          <code className="mt-2 block rounded-lg bg-bg px-2 py-2 font-mono text-[12px] text-fg">
            HIERARCHY_TOKEN=… PYTHONPATH=src python3 -m hierarchy serve --host 0.0.0.0 --port 8765
          </code>
        </div>
      </div>
    </Screen>
  );
}

export function ProvidersScreen({
  auth,
  onBack,
  onSaveKey,
  onUse,
  onOauth,
}: {
  auth: AuthStatus | null;
  onBack: () => void;
  onSaveKey: (provider: "xai" | "openai" | "openrouter", key: string) => void;
  onUse: (provider: string) => void;
  onOauth: (provider: "grok" | "chatgpt") => void;
}) {
  const [key, setKey] = useState("");
  const [prov, setProv] = useState<"xai" | "openai" | "openrouter">("xai");
  return (
    <Screen>
      <TopBar onBack={onBack} title="Providers" subtitle="xAI and ChatGPT" />
      <div className="space-y-4 px-4 py-4">
        <p className="text-[13px] leading-relaxed text-muted">
          OAuth uses the same public device-code clients as Grok CLI and Codex. Tokens are stored on the VPS at
          ~/.hierarchy/auth.json.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <PrimaryButton onClick={() => onOauth("grok")}>Grok OAuth</PrimaryButton>
          <GhostButton onClick={() => onOauth("chatgpt")}>ChatGPT OAuth</GhostButton>
        </div>
        <div className="rounded-[24px] border border-line bg-surface p-4">
          <Field label="API key fallback">
            <select
              value={prov}
              onChange={(e) => setProv(e.target.value as typeof prov)}
              className="mb-2 h-12 w-full rounded-[16px] border border-line bg-bg px-3 text-[15px]"
            >
              <option value="xai">xAI</option>
              <option value="openai">OpenAI</option>
              <option value="openrouter">OpenRouter</option>
            </select>
            <TextField
              type="password"
              value={key}
              placeholder="Paste key"
              onChange={(e) => setKey(e.target.value)}
            />
          </Field>
          <PrimaryButton
            className="mt-3"
            disabled={!key.trim()}
            onClick={() => {
              onSaveKey(prov, key.trim());
              setKey("");
            }}
          >
            Save key
          </PrimaryButton>
        </div>
        <div className="text-[13px] text-muted">
          Active: <span className="text-fg">{auth?.active || "stub"}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {["stub", "xai", "openai", "openrouter", "grok", "chatgpt"].map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onUse(p)}
              className="rounded-full bg-elevated px-3 py-1.5 text-[12px] capitalize"
            >
              {p}
            </button>
          ))}
        </div>
      </div>
    </Screen>
  );
}

export function OauthScreen({
  provider,
  userCode,
  uri,
  pending,
  onBack,
}: {
  provider: "grok" | "chatgpt";
  userCode: string;
  uri: string;
  pending: boolean;
  onBack: () => void;
}) {
  return (
    <Screen>
      <TopBar onBack={onBack} title={provider === "grok" ? "Grok OAuth" : "ChatGPT OAuth"} />
      <div className="flex flex-1 flex-col items-center px-6 py-10 text-center">
        <p className="text-[14px] text-muted">Open the verification page and enter this code</p>
        <div className="mt-6 text-[40px] font-semibold tracking-[0.12em]">{userCode || "····"}</div>
        {uri ? (
          <a
            href={uri}
            target="_blank"
            rel="noreferrer"
            className="mt-4 text-[14px] font-medium underline underline-offset-4"
          >
            Open {new URL(uri, "https://auth.x.ai").host}
          </a>
        ) : null}
        <p className="mt-8 text-[13px] text-muted">
          {pending ? "Waiting for approval on the VPS…" : "Connected."}
        </p>
      </div>
    </Screen>
  );
}

export function NewAgentScreen({
  bots,
  onBack,
  onCreate,
}: {
  bots: Bot[];
  onBack: () => void;
  onCreate: (input: { name: string; job: string; description: string; reports_to?: string }) => void;
}) {
  const [name, setName] = useState("");
  const [job, setJob] = useState("");
  const [description, setDescription] = useState("");
  const [reports, setReports] = useState("");
  return (
    <Screen>
      <TopBar onBack={onBack} title="New agent" />
      <form
        className="flex flex-1 flex-col gap-4 px-4 py-4"
        onSubmit={(e) => {
          e.preventDefault();
          onCreate({
            name,
            job,
            description,
            reports_to: reports || undefined,
          });
        }}
      >
        <Field label="Name">
          <TextField value={name} onChange={(e) => setName(e.target.value)} placeholder="Piper" />
        </Field>
        <Field label="Primary job">
          <TextField value={job} onChange={(e) => setJob(e.target.value)} placeholder="Product performance" />
        </Field>
        <Field label="How it should work">
          <AreaField
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Investigate using our tools. Never change production."
          />
        </Field>
        <Field label="Reports to">
          <select
            value={reports}
            onChange={(e) => setReports(e.target.value)}
            className="h-12 w-full rounded-[16px] border border-line bg-surface px-3 text-[15px]"
          >
            <option value="">None</option>
            {bots.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="mt-auto">
          <PrimaryButton type="submit" disabled={!name.trim() || !job.trim() || !description.trim()}>
            Create agent
          </PrimaryButton>
        </div>
      </form>
    </Screen>
  );
}

export function NewGroupScreen({
  bots,
  onBack,
  onCreate,
}: {
  bots: Bot[];
  onBack: () => void;
  onCreate: (name: string, memberIds: string[]) => void;
}) {
  const [name, setName] = useState("");
  const [ids, setIds] = useState<string[]>([]);
  function toggle(id: string) {
    setIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }
  return (
    <Screen>
      <TopBar onBack={onBack} title="New group chat" />
      <div className="flex flex-1 flex-col gap-4 px-4 py-4">
        <Field label="Name">
          <TextField value={name} onChange={(e) => setName(e.target.value)} placeholder="Launch floor" />
        </Field>
        <p className="text-[13px] text-muted">Select two to six bots</p>
        <div className="space-y-1">
          {bots.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => toggle(b.id)}
              className="flex w-full items-center gap-3 rounded-[16px] px-2 py-2 text-left"
            >
              <BotAvatar name={b.name} size="sm" />
              <span className="flex-1 text-[15px]">{b.name}</span>
              <span
                className={cn(
                  "size-5 rounded-full border",
                  ids.includes(b.id) ? "border-fg bg-fg" : "border-line",
                )}
              />
            </button>
          ))}
        </div>
        <PrimaryButton
          disabled={ids.length < 2 || !name.trim()}
          onClick={() => onCreate(name.trim(), ids)}
        >
          Create group
        </PrimaryButton>
      </div>
    </Screen>
  );
}

export function ProjectScreen({
  bots,
  onBack,
  onKickoff,
}: {
  bots: Bot[];
  onBack: () => void;
  onKickoff: (name: string, outcome: string, leadId?: string) => void;
}) {
  const [name, setName] = useState("");
  const [outcome, setOutcome] = useState("");
  const lead = bots.find((b) => b.name.toLowerCase() === "atlas") ?? bots[0];
  return (
    <Screen>
      <TopBar onBack={onBack} title="Kick off a project" />
      <div className="flex flex-1 flex-col gap-4 px-4 py-4">
        <p className="text-[14px] leading-relaxed text-muted">
          Atlas gets the outcome. Specialists get the first slice. Work continues on the VPS after you leave.
        </p>
        <Field label="Project">
          <TextField value={name} onChange={(e) => setName(e.target.value)} placeholder="Hierarchy Android client" />
        </Field>
        <Field label="Outcome">
          <AreaField
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            placeholder="Ship a working agent floor that can chat, DM, and run on two VPS backends."
          />
        </Field>
        <p className="text-[13px] text-muted">Lead: {lead?.name || "first bot on the floor"}</p>
        <div className="mt-auto">
          <PrimaryButton
            disabled={!name.trim() || !outcome.trim()}
            onClick={() => onKickoff(name.trim(), outcome.trim(), lead?.id)}
          >
            Kick off
          </PrimaryButton>
        </div>
      </div>
    </Screen>
  );
}

export function SearchScreen({
  bots,
  groups,
  query,
  onQuery,
  onBack,
  onOpenBot,
  onOpenGroup,
}: {
  bots: Bot[];
  groups: Group[];
  query: string;
  onQuery: (q: string) => void;
  onBack: () => void;
  onOpenBot: (id: string) => void;
  onOpenGroup: (id: string) => void;
}) {
  const q = query.trim().toLowerCase();
  const botHits = q
    ? bots.filter((b) => `${b.name} ${b.job} ${b.preview}`.toLowerCase().includes(q))
    : bots;
  const groupHits = q ? groups.filter((g) => g.name.toLowerCase().includes(q)) : groups;
  return (
    <Screen>
      <TopBar onBack={onBack} title="Search" />
      <div className="px-4 py-3">
        <TextField value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Bots, files, routines" autoFocus />
      </div>
      <div>
        {groupHits.map((g) => (
          <button
            key={g.id}
            type="button"
            onClick={() => onOpenGroup(g.id)}
            className="flex w-full items-center gap-3 px-4 py-3 text-left"
          >
            <span className="text-[15px] font-medium">{g.name}</span>
            <span className="text-[12px] text-muted">Group</span>
          </button>
        ))}
        {botHits.map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => onOpenBot(b.id)}
            className="flex w-full items-center gap-3 px-4 py-3 text-left"
          >
            <BotAvatar name={b.name} size="sm" />
            <div>
              <div className="text-[15px] font-medium">{b.name}</div>
              <div className="text-[12px] text-muted">{b.job}</div>
            </div>
          </button>
        ))}
      </div>
    </Screen>
  );
}

export function ProfileScreen({
  bot,
  onBack,
  onComputer,
  onPin,
  onHide,
  pinned,
}: {
  bot: Bot;
  onBack: () => void;
  onComputer: () => void;
  onPin: () => void;
  onHide: () => void;
  pinned: boolean;
}) {
  return (
    <Screen>
      <TopBar onBack={onBack} title={bot.name} subtitle={bot.job} />
      <div className="flex flex-col items-center px-6 py-8 text-center">
        <BotAvatar name={bot.name} size="xl" />
        <p className="mt-4 text-[14px] leading-relaxed text-muted">{bot.description}</p>
        {bot.reports_to ? <p className="mt-2 text-[12px] text-subtle">Reports to a lead on the floor</p> : null}
      </div>
      <div className="space-y-2 px-4">
        <GhostButton onClick={onComputer}>Open computer</GhostButton>
        <GhostButton onClick={onPin}>{pinned ? "Unpin conversation" : "Pin conversation"}</GhostButton>
        <GhostButton onClick={onHide}>Hide conversation</GhostButton>
      </div>
    </Screen>
  );
}

export function NewMenu({
  onClose,
  onAgent,
  onGroup,
  onProject,
}: {
  onClose: () => void;
  onAgent: () => void;
  onGroup: () => void;
  onProject: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-end bg-black/40" onClick={onClose}>
      <div
        className="w-full rounded-t-[28px] bg-surface px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />
        <button type="button" onClick={onAgent} className="block w-full py-3.5 text-left text-[16px] font-medium">
          New agent
        </button>
        <button type="button" onClick={onGroup} className="block w-full py-3.5 text-left text-[16px] font-medium">
          New group chat
        </button>
        <button type="button" onClick={onProject} className="block w-full py-3.5 text-left text-[16px] font-medium">
          Kick off a project
        </button>
        <button type="button" onClick={onClose} className="mt-2 block w-full py-3 text-left text-[15px] text-muted">
          Cancel
        </button>
      </div>
    </div>
  );
}

export function InstallScreen({ onBack }: { onBack: () => void }) {
  return (
    <Screen>
      <TopBar onBack={onBack} title="Install" subtitle="Android" />
      <div className="space-y-4 px-5 py-5 text-[15px] leading-relaxed">
        <p>
          Hierarchy is a phone app. Add it to your home screen for a full-screen Grok Bot floor, then point it at
          your VPS.
        </p>
        <ol className="list-decimal space-y-2 pl-5 text-[14px] text-muted">
          <li>Open this app in Chrome or the Grok browser.</li>
          <li>Tap the menu, then Install app or Add to Home screen.</li>
          <li>Open Hierarchy from the launcher.</li>
          <li>In Settings, set Primary and Backup agent URLs.</li>
        </ol>
        <a
          href="/hierarchy-agent.tgz"
          download="hierarchy-agent.tgz"
          className="flex h-12 w-full items-center justify-center rounded-[20px] bg-accent px-4 text-[15px] font-semibold text-accent-fg"
        >
          Download VPS agent
        </a>
        <div className="rounded-[20px] bg-elevated p-4 text-[13px] text-muted">
          Unpack it on your server, set a token, and run{" "}
          <span className="font-mono text-fg">python3 -m hierarchy serve</span>. Then paste the URL
          into Settings → Agent backends. This preview already has a demo computer so you can try
          the floor now.
        </div>
      </div>
    </Screen>
  );
}

export function GroupChatScreen({
  group,
  bots,
  history,
  draft,
  busy,
  onBack,
  onDraft,
  onSend,
}: {
  group: Group;
  bots: Bot[];
  history: { role: string; content: string; name?: string }[];
  draft: string;
  busy: boolean;
  onBack: () => void;
  onDraft: (v: string) => void;
  onSend: () => void;
}) {
  return (
    <Screen>
      <TopBar
        onBack={onBack}
        title={group.name}
        subtitle={group.memberIds
          .map((id) => bots.find((b) => b.id === id)?.name)
          .filter(Boolean)
          .join(", ")}
      />
      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-4">
        {history.map((item, i) => {
          const mine = item.role === "user";
          return (
            <div key={i} className={cn("flex", mine ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[82%] whitespace-pre-wrap rounded-[22px] px-3.5 py-2.5 text-[15px]",
                  mine ? "bg-user text-user-fg" : "bg-bubble text-fg",
                )}
              >
                {!mine && item.name ? (
                  <div className="mb-1 text-[11px] font-semibold text-muted">{item.name}</div>
                ) : null}
                {item.content}
              </div>
            </div>
          );
        })}
        {busy ? <p className="text-[13px] text-muted">Bots are handing this off…</p> : null}
      </div>
      <form
        className="flex items-end gap-2 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) onSend();
        }}
      >
        <div className="flex min-h-11 flex-1 items-end rounded-full bg-elevated px-1">
          <input
            value={draft}
            onChange={(e) => onDraft(e.target.value)}
            placeholder="Message the group, @name to mention"
            className="min-h-11 flex-1 bg-transparent px-3 py-2.5 text-[15px] outline-none placeholder:text-subtle"
            autoCapitalize="sentences"
          />
          <button
            type="submit"
            disabled={!draft.trim() || busy}
            className="mb-1 mr-1 grid size-9 place-items-center rounded-full bg-user text-user-fg disabled:opacity-30"
            aria-label="Send"
          >
            <SendHorizontal className="size-4" />
          </button>
        </div>
      </form>
    </Screen>
  );
}

export function useResolvedTheme(mode: AppearanceMode): "light" | "dark" {
  const [sys, setSys] = useState<"light" | "dark">("light");
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => setSys(mq.matches ? "dark" : "light");
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return mode === "system" ? sys : mode;
}
