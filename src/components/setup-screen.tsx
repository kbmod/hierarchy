import { useState } from "react";
import { AreaField, Banner, Field, GhostButton, PrimaryButton, Screen, TextField } from "@/components/chrome";
import { useApp } from "@/lib/store";
import { useAgent } from "@/lib/use-agent";
import { vps } from "@/lib/vps";

export function SetupScreen() {
  const vpsSlots = useApp((s) => s.vps);
  const upsertVps = useApp((s) => s.upsertVps);
  const complete = useApp((s) => s.completeOnboarding);
  const { run } = useAgent();
  const [step, setStep] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const primary = vpsSlots.find((v) => v.role === "primary") ?? vpsSlots[0];
  const backup = vpsSlots.find((v) => v.role === "backup") ?? vpsSlots[1];

  async function ping(slot = primary) {
    const url = slot.url.trim() || "demo";
    const result = await run(() => vps.health({ url, token: slot.token }), { quiet: false });
    if (result?.ok) {
      setNote(url === "demo" ? "Local demo computer is ready." : `Reached ${slot.label}.`);
      return true;
    }
    return false;
  }

  async function seedFloor() {
    const ok = await ping();
    if (!ok) return;
    const floor = await run(() => vps.floor({ url: primary.url || "demo", token: primary.token }));
    if (floor) complete();
  }

  return (
    <Screen className="px-5 pb-8 pt-[max(1.5rem,env(safe-area-inset-top))]">
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
            <PrimaryButton onClick={() => setStep(1)}>Configure computers</PrimaryButton>
            <GhostButton onClick={seedFloor}>Use the demo computer</GhostButton>
          </div>
        </>
      ) : null}

      {step === 1 ? (
        <>
          <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.03em]">Agent backends</h1>
          <p className="mt-2 text-[14px] text-muted">
            Paste the agent URL on each VPS. In this preview, leave the URL as{" "}
            <span className="font-medium text-fg">demo</span> to use the computer on this machine.
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
            {note ? <Banner>{note}</Banner> : null}
          </div>
          <div className="mt-auto space-y-3 pt-8">
            <PrimaryButton
              onClick={async () => {
                const ok = await ping();
                if (ok) setStep(2);
              }}
            >
              Test and continue
            </PrimaryButton>
            <GhostButton onClick={() => setStep(0)}>Back</GhostButton>
          </div>
        </>
      ) : null}

      {step === 2 ? (
        <>
          <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.03em]">Providers</h1>
          <p className="mt-2 text-[14px] leading-relaxed text-muted">
            Sign in with xAI (Grok) OAuth or ChatGPT OAuth on the VPS, or paste an API key. Tokens stay on the
            agent, never in the phone UI.
          </p>
          <p className="mt-4 text-[13px] text-muted">
            You can connect Grok and ChatGPT from Settings after the floor is up. This preview can use the
            bundled xAI key on the demo computer immediately.
          </p>
          <div className="mt-auto space-y-3 pt-8">
            <PrimaryButton onClick={() => setStep(3)}>Continue</PrimaryButton>
            <GhostButton onClick={() => setStep(1)}>Back</GhostButton>
          </div>
        </>
      ) : null}

      {step === 3 ? (
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
            <GhostButton onClick={() => setStep(2)}>Back</GhostButton>
          </div>
        </>
      ) : null}
    </Screen>
  );
}

function VpsFields({
  title,
  slot,
  onChange,
}: {
  title: string;
  slot: { id: string; label: string; url: string; token: string };
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
            placeholder="https://vps.example.net:8765 or demo"
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
