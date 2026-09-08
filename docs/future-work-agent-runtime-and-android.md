# Future work: real provider-backed agent runtime

Date: 2026-09-07
Repository: `kbmod/hierarchy`

## Scope of this note

This is a future-work record, not an acceptance report. It documents the gap
between the current implementation and the behavior wanted from Hierarchy:
independent Grok and ChatGPT subscription providers, a persistent multi-step
agent loop, explicit approvals, and a genuinely native Android client.

## Important finding about Hermes

The current work did **not** establish that Hierarchy's ChatGPT OAuth flow is
the same flow used by Hermes. The implementation currently contains a
Codex-style device-auth path and an optional Codex app-server backend. That is
not evidence that Hermes's default OAuth, provider abstraction, tool
execution, or session lifecycle has been borrowed correctly.

The current code should therefore be described precisely:

- Grok OAuth is implemented as a VPS-side device-code flow and has worked in
  the user's testing.
- ChatGPT has two different concepts in the current UI/runtime: a legacy
  Hierarchy HTTP OAuth path and an optional Codex app-server path.
- The Codex app-server path depends on the Codex installation and its own
  authenticated state; it is not currently a clearly actionable ChatGPT login
  flow in the Android UI.
- The repository has not yet demonstrated a live ChatGPT OAuth completion,
  per-bot ChatGPT execution, or Hermes-equivalent agent behavior.
- The current twelve-step runtime and synchronous chat behavior must not be
  presented as a completed autonomous-agent implementation.

The next investigation must obtain and inspect the actual Hermes
implementation (or a pinned, reviewable equivalent) before choosing protocol
details. Compare its OAuth start, browser/device callback, polling, token
refresh, account headers, provider selection, tool-call format, approval
handling, session persistence, and compaction behavior with
`vps-agent/src/hierarchy/oauth.py`, `llm.py`, and `runtime.py`. Record source
references and tests; do not infer equivalence from endpoint names or from the
fact that both projects can use a ChatGPT subscription.

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

1. ChatGPT subscription login completes through the verified implementation.
2. ChatGPT is selectable per bot independently of Grok.
3. Both providers execute native multi-step tool turns.
4. Soul, memory, session continuation, and compaction survive a resumed turn.
5. Approval requests appear as actionable Android controls and correctly pause
   and resume execution.
6. The native Android client works without relying on the shared WebView UI.

Until then, do not claim that Hermes has been successfully borrowed, that the
agent loop is complete, or that the current APK is a production-native client.
