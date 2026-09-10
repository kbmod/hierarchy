# Future work: real provider-backed agent runtime

Date: 2026-09-07
Repository: `kbmod/hierarchy`

## Scope of this note

This is both a current-state record and a future-work checklist. It documents
which Hermes runtime requirements now have evidence and which Grok Bot clone
requirements remain open.

## Verified Hermes integration (2026-09-08)

Hierarchy now installs and invokes NousResearch's actual Hermes Agent bot and
gateway implementation, pinned to commit
`966637323e6f90864e069dbc12755934c2c86387` (Hermes 0.21.1). The primary path is
Hermes `gateway run`, profile-scoped `/v1/runs`, `AIAgent`'s native tool loop,
and canonical Bot Mode sessions. It is not ACP or Codex app-server.

- Each supported Hierarchy bot maps to an isolated Hermes profile with a
  canonical `Bot Chat`, profile-scoped API key, `SOUL.md`, state database,
  memory, model/provider configuration, and shared-computer working directory.
- `chatgpt` maps to Hermes `openai-codex`; `grok` maps to Hermes `xai-oauth`.
  Their independent grants coexist in Hermes's private auth store and Hermes
  owns refresh after import.
- The existing device-login UI now saves completed grants and imports them into
  Hermes. Before this change, the HTTP poll endpoint discarded successful
  tokens instead of persisting them.
- A live ChatGPT subscription run through the phone-facing Hierarchy API used
  native terminal tools to create and read a file, then returned
  `HERMES_AGENT_LOOP_OK`. A second live run invoked `hierarchy-bot list` and
  returned the correct five-bot count.
- A live Grok OAuth run through the same Hermes profile route used terminal
  tools to write and read `GROK_HERMES_AGENT_OK`, proving both subscription
  providers use the native Hermes tool loop.
- Persistent specialists can be created, listed, and messaged from an agent's
  terminal with the narrow `hierarchy-bot` control command. These are real
  Hierarchy roster entries backed by Hermes profiles, not ephemeral subagents.

The former Codex app-server and twelve-step JSON loop remain only as compatibility
fallbacks when Hermes is not configured. They are not the installed primary
runtime.

## Required future implementation

### 1. Borrow Hermes provider and OAuth semantics

- Reproduce the verified Hermes ChatGPT subscription login flow, including
  whichever browser callback or device authorization mechanism Hermes actually
  uses.
- Preserve Grok and ChatGPT credentials independently in the VPS store.
- Make provider assignment explicit per bot, with no hidden global-provider
  fallback when a bot has a selected provider.
- Expose clear connection state, login progress, expiry, refresh failures, and
  retry actions in the client.
- Add unit tests for start, pending, approval/completion, refresh, expiry,
  malformed responses, and simultaneous Grok + ChatGPT credentials.
- Add an installed-service end-to-end test for both providers before calling
  the feature working.

### 2. Build a real agent executor

The provider layer must support an actual agent turn, not only one
message/response exchange:

- Parse each provider's native tool-call/event format rather than requiring a
  fragile JSON string convention.
- Persist a session/thread identifier and tool-call state across requests.
- Continue tool execution until completion, an explicit pause, or a
  configurable safety budget; make the budget visible and resumable rather
  than returning an opaque "check the computer screen" message.
- Add durable per-bot `SOUL.md`/identity instructions and layered `MEMORY.md`
  or equivalent memory files, with documented precedence and safe size limits.
- Add conversation compaction/summarization that preserves goals, decisions,
  pending actions, tool results, and approval state.
- Make retries, malformed events, provider errors, cancellation, and service
  restarts recoverable without duplicating side effects.
- Keep each bot's workspace, history, credentials, and memory isolated.
- Validate with a multi-step repository task on both Grok and ChatGPT, including
  a resumed turn after a deliberate pause.

### 3. Add approval requests as a first-class feature

Approvals must be explicit and actionable instead of being silently denied:

- Add a server-side approval-request record with request ID, bot/session ID,
  action summary, risk category, created/expired timestamps, and a one-time
  decision state.
- Expose authenticated list, approve, deny, and cancel endpoints. Decisions
  must be bound to the originating bot/session and be idempotent.
- Pause the agent at an approval boundary and resume it with the recorded
  decision. Never treat a client-side boolean as authorization.
- Render pending requests in the Android UI with clear **Approve** and
  **Deny** buttons, details of the proposed action, expiry, and the resulting
  audit status.
- Test denial, expiry, duplicate taps, reconnects, service restarts, and a
  request from the wrong bot/session.

### 4. Replace the WebView/Capacitor client

The current Android deliverable is a Capacitor client sharing the web UI. A
future native-client project must replace that dependency for the production
Android experience:

- Implement native screens, navigation, networking, secure token storage,
  provider login state, bot selection, agent progress, approvals, and errors.
- Keep the VPS API contract versioned and usable without browser globals or
  WebView assumptions.
- Support deep links or the verified Hermes/Codex browser callback flow where
  required, with state/PKCE validation and no token leakage through logs.
- Add native offline/reconnect behavior and background-safe polling or push
  updates for agent and approval state.
- Build and test the native APK on a real device; verify that it can manage
  both providers and approve/resume a multi-step task.

### 5. Provide safe discovery of an already-installed service

Operators need a supported way to recover connection details for a service
that is already installed. This must not require rerunning
`install-service.sh`, which could rotate or overwrite credentials:

- Add a read-only status/discovery command or authenticated local operator
  endpoint that finds the existing service URL(s) and bearer-token state.
- Never rotate, regenerate, overwrite, or otherwise mutate the token during
  retrieval. The command must work against services installed before this
  feature exists.
- Redact the bearer token by default. Require an explicit, clearly labeled
  reveal/copy action to expose it, and avoid placing it in ordinary logs,
  shell history, URLs, or diagnostic output.
- Report Tailscale and public URLs separately and label which path is intended
  for use. Do not imply that a public URL is safe when the firewall does not
  permit it.
- Limit access to an authorized local operator using the service account,
  root-owned service metadata, or an equivalent narrowly scoped permission
  boundary. Do not make token discovery available to unauthenticated remote
  callers.
- Test read-only behavior, default redaction, explicit reveal/copy, existing
  installation compatibility, missing/ambiguous addresses, and unauthorized
  local users.

## Current scope versus future acceptance

The current tree may be used for initial VPS testing of the existing service,
Grok flow, provider data model, and Codex integration experiments. It is not
accepted for the requirements above until live tests demonstrate all of the
following:

1. **Passed:** ChatGPT subscription credentials execute through upstream Hermes.
2. **Passed:** ChatGPT is selectable per bot independently of Grok.
3. **Passed:** Both ChatGPT and Grok have installed native multi-step tool
   acceptance through the same Hermes gateway.
4. **Partial:** Hermes profile soul, memory, canonical session, and compaction
   facilities are wired, and the canonical Owl session resumed across a Hermes
   service reinstall/restart. Explicit memory recall and forced compaction
   acceptance remain to be recorded.
5. **Open:** Approval requests appear as actionable Android controls and correctly pause
   and resume execution.
6. **Open:** The native Android client works without relying on the shared WebView UI.

Until the open acceptance items pass, describe this as an upstream-Hermes agent
runtime milestone, not a completed Grok Bot clone or production-native client.
