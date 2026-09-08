import { useState } from "react";
import { Check, LoaderCircle, X } from "lucide-react";
import { Banner, Field, GhostButton, PrimaryButton, Screen, TextField } from "@/components/chrome";
import { VpsHowto } from "@/components/vps-howto";
import { isNativeApp } from "@/lib/native";
import { useApp } from "@/lib/store";
import type { VpsSlot } from "@/lib/types";
import { useAgent } from "@/lib/use-agent";
import { cn } from "@/lib/utils";
import { normalizeAgentUrl, vps, VpsError } from "@/lib/vps";

type CheckStatus = "pending" | "run" | "ok" | "fail" | "skip";

type CheckRow = {
  id: string;
  label: string;
  status: CheckStatus;
  detail?: string;
};

export function SetupScreen() {
  const vpsSlots = useApp((s) => s.vps);
  const upsertVps = useApp((s) => s.upsertVps);
  const complete = useApp((s) => s.completeOnboarding);
  const { run } = useAgent();
  const [step, setStep] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const [checks, setChecks] = useState<CheckRow[]>([]);
  const [testing, setTesting] = useState(false);
  const primary = vpsSlots.find((v) => v.role === "primary") ?? vpsSlots[0];
  const backup = vpsSlots.find((v) => v.role === "backup") ?? vpsSlots[1];
  const native = isNativeApp();

  async function testAndContinue() {
    const filled = vpsSlots.filter((s) => s.url.trim());
    if (filled.length === 0) {
      setNote("Paste at least one VPS URL (http://100.x.x.x:8765).");
      return;
    }
    setNote(null);
    let rows: CheckRow[] = [];
    for (const slot of vpsSlots) {
      if (!slot.url.trim()) {
        rows.push({
          id: `${slot.id}-skip`,
          label: `${slot.label}: skipped`,
          status: "skip",
          detail: "No URL — this box will not be used yet.",
        });
        continue;
      }
      rows.push({ id: `${slot.id}-url`, label: `${slot.label}: URL`, status: "pending" });
      rows.push({ id: `${slot.id}-health`, label: `${slot.label}: health`, status: "pending" });
      rows.push({ id: `${slot.id}-auth`, label: `${slot.label}: token`, status: "pending" });
    }
    setChecks(rows);
    setTesting(true);
    setStep(25);
    await new Promise((r) => setTimeout(r, 50));

    const update = (id: string, patch: Partial<CheckRow>) => {
      rows = rows.map((row) => (row.id === id ? { ...row, ...patch } : row));
      setChecks(rows);
    };

    async function runOne(id: string, fn: () => Promise<string>): Promise<boolean> {
      update(id, { status: "run", detail: undefined });
      try {
        const detail = await fn();
        update(id, { status: "ok", detail });
        return true;
      } catch (err) {
        const detail =
          err instanceof VpsError
            ? hint(err.message)
            : err instanceof Error
              ? hint(err.message)
              : "Unknown error";
        update(id, { status: "fail", detail });
        return false;
      }
    }

    try {
      for (const slot of vpsSlots) {
        if (!slot.url.trim()) continue;
        const urlOk = await runOne(`${slot.id}-url`, async () => {
          const normalized = normalizeAgentUrl(slot.url);
          new URL(normalized);
          if (normalized !== slot.url.trim()) {
            upsertVps({ ...slot, url: normalized });
          }
          return normalized;
        });
        if (!urlOk) {
          update(`${slot.id}-health`, { status: "fail", detail: "Skipped — URL is invalid." });
          update(`${slot.id}-auth`, { status: "fail", detail: "Skipped — URL is invalid." });
          continue;
        }
        const conn = { url: normalizeAgentUrl(slot.url), token: slot.token };
        const healthOk = await runOne(`${slot.id}-health`, async () => {
          const target = `${conn.url}/api/health`;
          try {
            const hit = await vps.health(conn, 20_000);
            if (!hit?.ok) throw new VpsError(`GET ${target} did not return ok.`);
            return `GET ${target} — ok${typeof hit.bots === "number" ? `, ${hit.bots} bots` : ""}.`;
          } catch (err) {
            const raw = err instanceof Error ? err.message : "unreachable";
            throw new VpsError(healthHint(conn.url, raw));
          }
        });
        if (!healthOk) {
          update(`${slot.id}-auth`, { status: "fail", detail: "Skipped — agent is not reachable." });
          continue;
        }
        await runOne(`${slot.id}-auth`, async () => {
          if (!slot.token.trim()) {
            throw new VpsError("No token pasted. Copy HIERARCHY_TOKEN from the installer.");
          }
          await vps.auth(conn);
          return "Token accepted.";
        });
      }
    } finally {
      setTesting(false);
    }
  }

  async function seedFloor() {
    const filled = vpsSlots.filter((s) => s.url.trim());
    const slot = filled[0] ?? primary;
    const url = slot?.url.trim() || (native ? "" : "demo");
    if (!url) {
      setNote("Paste the VPS URL first (http://YOUR_IP:8765).");
      return;
    }
    const floor = await run(() => vps.floor({ url: normalizeAgentUrl(url), token: slot.token }));
    if (floor) complete();
  }

  return (
    <Screen className="overflow-y-auto px-5 pb-8 pt-[max(1.5rem,env(safe-area-inset-top))]">
      <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-muted">Hierarchy</p>
      {step === 0 ? (
        <>
          <h1 className="mt-3 text-[32px] font-semibold leading-tight tracking-[-0.03em]">
            Bots on your own computers.
          </h1>
          <p className="mt-3 max-w-sm text-[15px] leading-relaxed text-muted">
            Named teammates on VPS hosts you own. Each bot can use Grok, ChatGPT, or an API key. The screen
            button is a shell on that machine — no desktop environment required.
          </p>
          <div className="mt-auto space-y-3 pt-10">
            <PrimaryButton onClick={() => setStep(1)}>Set up a VPS</PrimaryButton>
            {native ? null : <GhostButton onClick={seedFloor}>Use the demo computer</GhostButton>}
          </div>
        </>
      ) : null}

      {step === 1 ? (
        <>
          <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.03em]">On your VPS</h1>
          <div className="mt-4">
            <VpsHowto />
          </div>
          <div className="mt-auto space-y-3 pt-8">
            <PrimaryButton onClick={() => setStep(2)}>I have a URL and token</PrimaryButton>
            <GhostButton onClick={() => setStep(0)}>Back</GhostButton>
          </div>
        </>
      ) : null}

      {step === 2 ? (
        <>
          <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.03em]">Paste them here</h1>
          <p className="mt-2 text-[14px] text-muted">
            For Tailscale, paste <span className="font-medium text-fg">http://100.x.x.x:8765</span> from{" "}
            <span className="font-mono text-[12px] text-fg">tailscale ip -4</span> on the VPS — not the
            .ts.net name. MagicDNS often fails in this app. Empty backup is fine.
          </p>
          <div className="mt-6 space-y-5">
            {primary ? (
              <VpsFields
                title="Primary"
                slot={primary}
                onChange={(patch) => upsertVps({ ...primary, ...patch })}
              />
            ) : null}
            {backup ? (
              <VpsFields
                title="Backup"
                slot={backup}
                onChange={(patch) => upsertVps({ ...backup, ...patch })}
              />
            ) : null}
            {note ? <Banner tone="danger">{note}</Banner> : null}
          </div>
          <div className="mt-auto space-y-3 pt-8">
            <PrimaryButton disabled={testing} onClick={() => void testAndContinue()}>
              Test and continue
            </PrimaryButton>
            <GhostButton onClick={() => setStep(1)}>Back</GhostButton>
          </div>
        </>
      ) : null}

      {step === 25 ? (
        <>
          <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.03em]">Testing computers</h1>
          <p className="mt-2 text-[14px] text-muted">
            {testing ? "Checking each VPS…" : "Finished. Fix anything red, then retry."}
          </p>
          <ul className="mt-6 space-y-3">
            {checks.map((row) => (
              <li key={row.id} className="flex gap-3 rounded-[18px] bg-surface px-3 py-3">
                <CheckIcon status={row.status} />
                <div className="min-w-0 flex-1">
                  <div className="text-[14px] font-medium">{row.label}</div>
                  {row.detail ? (
                    <p
                      className={cn(
                        "mt-0.5 text-[13px] leading-snug",
                        row.status === "fail" ? "text-danger" : "text-muted",
                      )}
                    >
                      {row.detail}
                    </p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-auto space-y-3 pt-8">
            {!testing && checks.some((c) => c.status === "fail") ? (
              <>
                <PrimaryButton onClick={() => void testAndContinue()}>Retry tests</PrimaryButton>
                <GhostButton onClick={() => setStep(2)}>Edit URLs</GhostButton>
              </>
            ) : null}
            {!testing && checks.length > 0 && checks.every((c) => c.status === "ok" || c.status === "skip") ? (
              <PrimaryButton onClick={() => setStep(3)}>Continue</PrimaryButton>
            ) : null}
            {testing ? (
              <p className="text-center text-[13px] text-muted">Do not leave this screen…</p>
            ) : null}
          </div>
        </>
      ) : null}

      {step === 3 ? (
        <>
          <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.03em]">Providers</h1>
          <p className="mt-2 text-[14px] leading-relaxed text-muted">
            Sign in with Grok OAuth or ChatGPT OAuth after the floor is up (Settings → Providers), or paste an
            API key there. Tokens stay on the VPS, not on the phone.
          </p>
          <div className="mt-auto space-y-3 pt-8">
            <PrimaryButton onClick={() => setStep(4)}>Continue</PrimaryButton>
            <GhostButton onClick={() => setStep(2)}>Back</GhostButton>
          </div>
        </>
      ) : null}

      {step === 4 ? (
        <>
          <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.03em]">Meet the floor</h1>
          <p className="mt-2 text-[14px] leading-relaxed text-muted">
            Atlas routes. Forge writes. Scout verifies. Quill drafts. You assign an outcome; they do the work
            on the shared computer.
          </p>
          <ul className="mt-6 space-y-3 text-[14px]">
            <li>
              <span className="font-semibold">Atlas</span>
              <span className="text-muted"> — Chief of Staff</span>
            </li>
            <li>
              <span className="font-semibold">Forge</span>
              <span className="text-muted"> — Engineer</span>
            </li>
            <li>
              <span className="font-semibold">Scout</span>
              <span className="text-muted"> — Researcher</span>
            </li>
            <li>
              <span className="font-semibold">Quill</span>
              <span className="text-muted"> — Writer</span>
            </li>
          </ul>
          <div className="mt-auto space-y-3 pt-8">
            <PrimaryButton onClick={seedFloor}>Create teammates</PrimaryButton>
            <GhostButton onClick={() => setStep(3)}>Back</GhostButton>
          </div>
        </>
      ) : null}
    </Screen>
  );
}

function CheckIcon({ status }: { status: CheckStatus }) {
  if (status === "run") {
    return <LoaderCircle className="mt-0.5 size-5 shrink-0 animate-spin text-muted" />;
  }
  if (status === "ok") {
    return <Check className="mt-0.5 size-5 shrink-0 text-ok" />;
  }
  if (status === "fail") {
    return <X className="mt-0.5 size-5 shrink-0 text-danger" />;
  }
  return <span className="mt-0.5 size-5 shrink-0 rounded-full border border-line" />;
}

function hint(message: string): string {
  if (message.includes("MagicDNS") || message.includes("tailscale ip")) return message;
  return healthHint("", message);
}

function healthHint(url: string, message: string): string {
  const lower = message.toLowerCase();
  const magic = /\.ts\.net(?::|\/|$)/i.test(url);
  if (magic) {
    return (
      `${message} GET ${url}/api/health. Android often cannot resolve Tailscale MagicDNS ` +
      `(*.ts.net) inside this app. On the VPS run: tailscale ip -4   then paste ` +
      `http://THAT_100_ADDRESS:8765 instead. Keep the Tailscale app connected on the phone.`
    );
  }
  if (lower.includes("failed to fetch") || lower.includes("network") || lower.includes("load")) {
    return `${message} — the phone cannot reach that address. On Tailscale, connect the Tailscale app and use the 100.x.x.x IP, not a .ts.net name.`;
  }
  if (lower.includes("unauthorized") || lower.includes("401")) {
    return `${message} — token does not match HIERARCHY_TOKEN on the VPS.`;
  }
  if (lower.includes("timeout")) {
    return `${message} — no answer from ${url || "the agent"} in 20s. Confirm hierarchy.service is running and the phone is on Tailscale. Prefer http://100.x.x.x:8765 over a .ts.net name.`;
  }
  return message;
}

function VpsFields({
  title,
  slot,
  onChange,
}: {
  title: string;
  slot: VpsSlot;
  onChange: (patch: { label?: string; url?: string; token?: string }) => void;
}) {
  return (
    <div className="rounded-[24px] border border-line bg-surface p-4">
      <div className="mb-3 text-[13px] font-semibold">{title}</div>
      <div className="space-y-3">
        <Field label="Label">
          <TextField value={slot.label} onChange={(e) => onChange({ label: e.target.value })} />
        </Field>
        <Field label="Agent URL">
          <TextField
            value={slot.url}
            placeholder="http://100.x.x.x:8765"
            onChange={(e) => onChange({ url: e.target.value })}
            autoCapitalize="none"
            autoCorrect="off"
          />
        </Field>
        <Field label="Token">
          <TextField
            type="password"
            value={slot.token}
            placeholder="HIERARCHY_TOKEN"
            onChange={(e) => onChange({ token: e.target.value })}
            autoCapitalize="none"
            autoCorrect="off"
          />
        </Field>
      </div>
    </div>
  );
}
