import { useCallback, useEffect, useMemo, useState } from "react";
import { ChatScreen } from "@/components/chat-screen";
import { ShellScreen } from "@/components/computer-screen";
import { HomeScreen } from "@/components/home-screen";
import {
  BackendsScreen,
  GroupChatScreen,
  InstallScreen,
  NewAgentScreen,
  NewGroupScreen,
  NewMenu,
  OauthScreen,
  ProfileScreen,
  ProjectScreen,
  ProvidersScreen,
  SearchScreen,
  SettingsScreen,
  useResolvedTheme,
} from "@/components/more-screens";
import { SetupScreen } from "@/components/setup-screen";
import { Banner } from "@/components/chrome";
import type { AuthStatus, Bot, HistoryItem, ShellState } from "@/lib/types";
import { useApp } from "@/lib/store";
import { uid } from "@/lib/utils";
import { slotConn, useAgent } from "@/lib/use-agent";
import { isNativeApp } from "@/lib/native";
import { vps } from "@/lib/vps";

export function HierarchyApp() {
  const stack = useApp((s) => s.stack);
  const appearance = useApp((s) => s.appearance);
  const hydrate = useApp((s) => s.hydrate);
  const go = useApp((s) => s.go);
  const back = useApp((s) => s.back);
  const resetTo = useApp((s) => s.resetTo);
  const busy = useApp((s) => s.busy);
  const error = useApp((s) => s.error);
  const drafts = useApp((s) => s.drafts);
  const setDraft = useApp((s) => s.setDraft);
  const groups = useApp((s) => s.groups);
  const addGroup = useApp((s) => s.addGroup);
  const updateGroup = useApp((s) => s.updateGroup);
  const pinned = useApp((s) => s.pinned);
  const hidden = useApp((s) => s.hidden);
  const togglePin = useApp((s) => s.togglePin);
  const hideConv = useApp((s) => s.hideConv);
  const vpsSlots = useApp((s) => s.vps);
  const activeVpsId = useApp((s) => s.activeVpsId);
  const setActiveVps = useApp((s) => s.setActiveVps);
  const onboarded = useApp((s) => s.onboarded);
  const { conn, connFor, run } = useAgent();
  const theme = useResolvedTheme(appearance);

  const [bots, setBots] = useState<Bot[]>([]);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authByVps, setAuthByVps] = useState<Record<string, AuthStatus>>({});
  const [history, setHistory] = useState<Record<string, HistoryItem[]>>({});
  const [shell, setShell] = useState<ShellState | null>(null);
  const [menu, setMenu] = useState(false);
  const [query, setQuery] = useState("");
  const [healthNote, setHealthNote] = useState<string | null>(null);
  const [oauth, setOauth] = useState<{
    session: string;
    user_code: string;
    uri: string;
    pending: boolean;
  } | null>(null);
  const [groupHist, setGroupHist] = useState<Record<string, { role: string; content: string; name?: string }[]>>(
    {},
  );
  const [attachNote, setAttachNote] = useState<string | null>(null);
  const screen = stack[stack.length - 1] ?? { name: "home" as const };

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!isNativeApp()) return;
    const cap = (
      window as unknown as {
        Capacitor?: { Plugins?: { App?: { addListener?: (event: string, cb: () => void) => { remove?: () => void } } } };
      }
    ).Capacitor;
    const handle = cap?.Plugins?.App?.addListener?.("backButton", () => {
      if (useApp.getState().stack.length > 1) back();
    });
    return () => {
      handle?.remove?.();
    };
  }, [back]);

  const refresh = useCallback(async () => {
    const slots = vpsSlots.filter((s) => s.url.trim());
    const lists = await Promise.all(
      slots.map(async (slot) => {
        try {
          const roster = await vps.bots(slotConn(slot));
          return roster.bots.map((b) => ({ ...b, vpsId: slot.id }));
        } catch {
          return [];
        }
      }),
    );
    setBots(lists.flat());
    const auths: Record<string, AuthStatus> = {};
    await Promise.all(
      slots.map(async (slot) => {
        try {
          auths[slot.id] = await vps.auth(slotConn(slot));
        } catch {
          /* skip unreachable */
        }
      }),
    );
    setAuthByVps(auths);
    setAuth(auths[useApp.getState().activeVpsId] ?? Object.values(auths)[0] ?? null);
  }, [vpsSlots]);

  useEffect(() => {
    if (onboarded) void refresh();
  }, [refresh, onboarded, conn.url, conn.token]);

  const shellVpsId = screen.name === "computer" ? screen.vpsId : undefined;
  const shellConn = connFor(shellVpsId);

  useEffect(() => {
    if (screen.name !== "computer") return;
    const tick = () => {
      void run(() => vps.computer(shellConn), { quiet: true }).then((data) => {
        if (data) setShell(data);
      });
    };
    tick();
    const id = window.setInterval(tick, 2000);
    return () => window.clearInterval(id);
  }, [screen.name, shellConn.url, shellConn.token, run]);

  const currentBot = useMemo(() => {
    if (screen.name === "chat" || screen.name === "profile") {
      const id = "botId" in screen ? screen.botId : undefined;
      return bots.find((b) => b.id === id) ?? bots[0];
    }
    return undefined;
  }, [screen, bots]);

  function botConn(botId: string) {
    const bot = bots.find((b) => b.id === botId);
    return connFor(bot?.vpsId);
  }

  async function openBot(id: string) {
    go({ name: "chat", botId: id });
    const data = await run(() => vps.history(botConn(id), id), { quiet: true });
    if (data) {
      setHistory((h) => {
        const local = h[id] || [];
        if (local.length > data.history.length) return h;
        return { ...h, [id]: data.history };
      });
    }
  }

  async function waitJob(jobId: string, botId: string) {
    const c = botConn(botId);
    for (let i = 0; i < 90; i += 1) {
      await new Promise((r) => setTimeout(r, 1200));
      const job = await run(() => vps.job(c, jobId), { quiet: true });
      const hist = await run(() => vps.history(c, botId), { quiet: true });
      if (hist) {
        setHistory((h) => ({ ...h, [botId]: hist.history }));
      }
      if (job && job.status !== "working") {
        if (job.status === "error" && job.error) {
          useApp.getState().setError(job.error);
        }
        return;
      }
    }
  }

  async function sendChat(botId: string) {
    const text = (drafts[botId] || "").trim();
    if (!text) return;
    setDraft(botId, "");
    setHistory((h) => ({
      ...h,
      [botId]: [...(h[botId] || []), { role: "user", content: text }],
    }));
    const reply = await run(() => vps.chat(botConn(botId), botId, text));
    if (!reply) return;
    if (reply.job_id) {
      useApp.getState().setBusy(true);
      try {
        await waitJob(reply.job_id, botId);
      } finally {
        useApp.getState().setBusy(false);
      }
    } else if (reply.text) {
      setHistory((h) => ({
        ...h,
        [botId]: [...(h[botId] || []), { role: "assistant", content: reply.text }],
      }));
    }
    await refresh();
  }

  async function refreshShell(vpsId?: string) {
    const data = await run(() => vps.computer(connFor(vpsId)), { quiet: true });
    if (data) setShell(data);
  }

  async function openComputer(vpsId?: string) {
    go({ name: "computer", vpsId });
    await refreshShell(vpsId);
  }

  async function startOauth(provider: "grok" | "chatgpt") {
    const start = await run(() => vps.oauthStart(conn, provider));
    if (!start) return;
    setOauth({
      session: start.session,
      user_code: start.user_code,
      uri: start.verification_uri,
      pending: true,
    });
    go({ name: "oauth", provider });
    const tick = async () => {
      const polled = await run(() => vps.oauthPoll(conn, start.session), { quiet: true });
      if (polled?.ok) {
        setOauth((o) => (o ? { ...o, pending: false } : o));
        await refresh();
        return;
      }
      setTimeout(tick, 3000);
    };
    setTimeout(tick, 2500);
  }

  async function kickoff(name: string, outcome: string, leadId?: string) {
    const lead = bots.find((b) => b.id === leadId);
    const result = await run(() =>
      vps.kickoff(connFor(lead?.vpsId), { name, outcome, lead_id: leadId }),
    );
    if (!result) return;
    await refresh();
    const leadBot = result.lead.bot_id;
    setHistory((h) => ({
      ...h,
      [leadBot]: [
        ...(h[leadBot] || []),
        { role: "user", content: `Project ${name}: ${outcome}` },
        { role: "assistant", content: result.lead.text },
      ],
    }));
    if (result.specialist) {
      const sid = result.specialist.bot_id;
      setHistory((h) => ({
        ...h,
        [sid]: [...(h[sid] || []), { role: "assistant", content: result.specialist!.text }],
      }));
    }
    resetTo({ name: "chat", botId: leadBot });
  }

  async function sendGroup(groupId: string) {
    const group = groups.find((g) => g.id === groupId);
    if (!group) return;
    const text = (drafts[groupId] || "").trim();
    if (!text) return;
    setDraft(groupId, "");
    setGroupHist((h) => ({
      ...h,
      [groupId]: [...(h[groupId] || []), { role: "user", content: text }],
    }));
    const mention = text.match(/@([A-Za-z0-9_-]+)/);
    let targets = group.memberIds;
    if (mention && mention[1].toLowerCase() !== "everyone") {
      const named = bots.find((b) => b.name.toLowerCase() === mention[1].toLowerCase());
      if (named) targets = [named.id];
    }
    for (const id of targets) {
      const reply = await run(() => vps.chat(botConn(id), id, `[group ${group.name}] ${text}`));
      if (reply) {
        const bot = bots.find((b) => b.id === id);
        setGroupHist((h) => ({
          ...h,
          [groupId]: [...(h[groupId] || []), { role: "assistant", content: reply.text, name: bot?.name }],
        }));
      }
    }
    updateGroup(groupId, { preview: text, updatedAt: Date.now() });
  }

  const groupId = screen.name === "group" ? screen.groupId : "";
  const activeGroup = groups.find((g) => g.id === groupId);

return (
    <div data-theme={theme} className="phone-frame mx-auto min-h-dvh max-w-lg bg-bg text-fg antialiased">
      {screen.name === "setup" ? <SetupScreen /> : null}

      {screen.name === "home" ? (
        <HomeScreen
          bots={bots}
          groups={groups}
          hidden={hidden}
          pinned={pinned}
          vpsLabel={(id) => vpsSlots.find((s) => s.id === id)?.label || ""}
          onOpenBot={openBot}
          onOpenGroup={(id) => go({ name: "group", groupId: id })}
          onSearch={() => go({ name: "search" })}
          onNew={() => setMenu(true)}
          onSettings={() => go({ name: "settings" })}
          onComputer={() => openComputer()}
        />
      ) : null}

      {screen.name === "chat" && currentBot ? (
        <ChatScreen
          bot={currentBot}
          history={history[currentBot.id] || []}
          draft={drafts[currentBot.id] || ""}
          busy={busy}
          error={error}
          onBack={back}
          onDraft={(v) => setDraft(currentBot.id, v)}
          onSend={() => sendChat(currentBot.id)}
          onComputer={() => openComputer(currentBot.vpsId)}
          onProfile={() => go({ name: "profile", botId: currentBot.id })}
          onAttach={() =>
            setAttachNote("Photos and files attach on the VPS computer, not this preview camera.")
          }
        />
      ) : null}

      {screen.name === "computer" ? (
        <ShellScreen
          shell={shell}
          busy={busy}
          onBack={back}
          onExec={async (cmd) => {
            const result = await run(() => vps.exec(shellConn, cmd));
            if (result) setShell(result);
          }}
        />
      ) : null}

      {screen.name === "settings" ? (
        <SettingsScreen auth={auth} onBack={back} onOpen={(name) => go({ name })} />
      ) : null}

      {screen.name === "backends" ? (
        <BackendsScreen
          healthNote={healthNote}
          onBack={back}
          onTest={async (id) => {
            const slot = vpsSlots.find((v) => v.id === id);
            if (!slot) return;
            setActiveVps(id);
            const ping = await run(() => vps.health({ url: slot.url || "demo", token: slot.token }));
            setHealthNote(ping?.ok ? `${slot.label} is reachable.` : "Unreachable.");
          }}
        />
      ) : null}

      {screen.name === "providers" ? (
        <ProvidersScreen
          auth={auth}
          onBack={back}
          onSaveKey={async (provider, key) => {
            const status = await run(() => vps.setKey(conn, provider, key));
            if (status) setAuth(status);
          }}
          onUse={async (provider) => {
            const status = await run(() => vps.useProvider(conn, provider));
            if (status) setAuth(status);
          }}
          onOauth={startOauth}
        />
      ) : null}

      {screen.name === "oauth" && oauth ? (
        <OauthScreen
          provider={screen.provider}
          userCode={oauth.user_code}
          uri={oauth.uri}
          pending={oauth.pending}
          onBack={back}
        />
      ) : null}

      {screen.name === "new-agent" ? (
        <NewAgentScreen
          bots={bots}
          auth={auth}
          authByVps={authByVps}
          computers={vpsSlots.filter((s) => s.url.trim())}
          defaultVpsId={activeVpsId}
          onBack={back}
          onCreate={async (input) => {
            const created = await run(() => vps.createBot(connFor(input.vpsId), input));
            if (created) {
              await refresh();
              resetTo({ name: "chat", botId: created.id });
            }
          }}
        />
      ) : null}

      {screen.name === "new-group" ? (
        <NewGroupScreen
          bots={bots}
          onBack={back}
          onCreate={(name, memberIds) => {
            const id = uid();
            addGroup({ id, name, memberIds, preview: "New group", updatedAt: Date.now() });
            resetTo({ name: "group", groupId: id });
          }}
        />
      ) : null}

      {screen.name === "project" ? <ProjectScreen bots={bots} onBack={back} onKickoff={kickoff} /> : null}

      {screen.name === "search" ? (
        <SearchScreen
          bots={bots}
          groups={groups}
          query={query}
          onQuery={setQuery}
          onBack={back}
          onOpenBot={openBot}
          onOpenGroup={(id) => go({ name: "group", groupId: id })}
        />
      ) : null}

      {screen.name === "profile" && currentBot ? (
        <ProfileScreen
          bot={currentBot}
          auth={authByVps[currentBot.vpsId || ""] ?? auth}
          computerLabel={vpsSlots.find((s) => s.id === currentBot.vpsId)?.label}
          pinned={pinned.includes(currentBot.id)}
          onBack={back}
          onComputer={() => openComputer(currentBot.vpsId)}
          onSaveModel={async (provider, model) => {
            const updated = await run(() =>
              vps.updateBot(connFor(currentBot.vpsId), currentBot.id, { provider, model }),
            );
            if (updated) await refresh();
          }}
          onPin={() => togglePin(currentBot.id)}
          onHide={() => {
            hideConv(currentBot.id);
            resetTo({ name: "home" });
          }}
        />
      ) : null}

      {screen.name === "install" ? <InstallScreen onBack={back} /> : null}

      {screen.name === "group" && activeGroup ? (
        <GroupChatScreen
          group={activeGroup}
          bots={bots}
          history={groupHist[activeGroup.id] || []}
          draft={drafts[activeGroup.id] || ""}
          busy={busy}
          onBack={back}
          onDraft={(v) => setDraft(activeGroup.id, v)}
          onSend={() => sendGroup(activeGroup.id)}
        />
      ) : null}

      {menu ? (
        <NewMenu
          onClose={() => setMenu(false)}
          onAgent={() => {
            setMenu(false);
            go({ name: "new-agent" });
          }}
          onGroup={() => {
            setMenu(false);
            go({ name: "new-group" });
          }}
          onProject={() => {
            setMenu(false);
            go({ name: "project" });
          }}
        />
      ) : null}

      {attachNote ? (
        <button type="button" className="fixed inset-x-4 bottom-24 z-30" onClick={() => setAttachNote(null)}>
          <Banner>{attachNote}</Banner>
        </button>
      ) : null}

      {error ? (
        <div className="fixed inset-x-4 bottom-24 z-30">
          <Banner tone="danger">{error}</Banner>
        </div>
      ) : null}
    </div>
  );
}
