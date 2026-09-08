# Hierarchy Continuity Log

Date: 2026-09-07
Repository: `kbmod/hierarchy`
Current branch: `main`
Current checkout: `69ed35c` (`origin/main` also points to `69ed35c` at audit time)

## Purpose

This log preserves the current implementation state, the provider/agent-loop investigation, the network incident diagnosis, and the next steps for moving Hierarchy development to another VPS.

It deliberately separates verified repository facts, user observations, hypotheses, and work that remains unverified.

## Repository state

Verified from the current checkout:

- `main` has no commits ahead of `origin/main`.
- The disk contains uncommitted work newer than GitHub `main`.
- `git diff --check` passed for the current tracked diff before this document was added.
- Before this document was added, the worktree had ten modified files:

  - `capacitor.config.ts`
  - `src/components/hierarchy-app.tsx`
  - `src/components/setup-screen.tsx`
  - `src/components/vps-howto.tsx`
  - `src/lib/server/proxy.ts`
  - `src/lib/vps.ts`
  - `startup.sh`
  - `vps-agent/src/hierarchy/llm.py`
  - `vps-agent/src/hierarchy/oauth.py`
  - `vps-agent/tests/test_auth.py`

- Before this document was added, the untracked files were:

  - `start.md`
  - `scripts/startup-contract.test.mjs`

- This document is now an additional untracked file until intentionally staged.
- No secrets, OAuth tokens, or `~/.hierarchy` runtime state should be committed.

## Recent committed milestones

- `5c48049` — initial repository
- `a77fe9f` — standalone multi-bot runtime with keys and OAuth
- `e101266` — web client and Python agent moved into `vps-agent/`
- `81a426d` — Android client, VPS shell, and per-bot provider/model support
- `69ed35c` — systemd installer and pinning each bot to a VPS

## Current implementation

The application consists of:

- An Android Capacitor client.
- A web preview using the same UI.
- A Python VPS runtime under `vps-agent/`.
- A systemd service installed by `vps-agent/scripts/install-service.sh`.
- A per-VPS store under `~/.hierarchy`.
- Bot identity, instructions, history, computer state, inboxes, and routines stored on disk.

The runtime uses `ThreadingHTTPServer` and listens on port `8765` when installed as a service.

The web preview demo was moved to port `18765` so it does not conflict with the real VPS agent on `8765`.

The Android client uses native HTTP for remote VPS URLs. Remote URLs are normalized, while the preview-only demo remains local.

## Provider state

### Verified repository behavior

The VPS auth store supports independent credentials for both OAuth providers:

- `oauth.grok`
- `oauth.chatgpt`

`auth.credential(home, provider=...)` resolves a specific provider when a bot has one assigned. The VPS-wide `active` provider is only the fallback/default.

The `Bot` model has:

- `provider`
- `model`

The runtime passes the bot's selected provider into credential resolution. The data model and runtime are therefore designed to allow Grok and ChatGPT to coexist and to be selected independently per bot.

The current UI includes provider/model selection when creating a bot and when editing a bot profile. It also displays whether a provider is connected. This behavior has not yet been accepted by a live end-to-end test.

### Grok OAuth

User-observed result:

- Grok OAuth starts and connects successfully.

Repository implementation:

- Uses xAI device-code OAuth.
- Stores the resulting token on the VPS.
- Uses the xAI OpenAI-compatible chat-completions endpoint.

### ChatGPT OAuth

User-observed result:

- The ChatGPT OAuth button appears to do nothing.
- It has not been confirmed that ChatGPT OAuth completes or stores a token.
- The failure is not explained by Grok already being configured; the auth store is intended to retain both providers.

Current implementation:

- Uses the Codex-style device-auth endpoints.
- Uses the public Codex client ID.
- Polls the device-auth token endpoint.
- Exchanges the authorization code at the OpenAI OAuth token endpoint.
- Sends Codex-style headers, including `originator: codex_cli_rs`.
- Calls `https://chatgpt.com/backend-api/codex/responses` for ChatGPT OAuth model requests.

The dirty worktree contains a recent attempted fix for the ChatGPT flow:

- Added Codex-style headers.
- Removed `client_id` from the device-auth polling payload.
- Changed the handling of HTTP 400 responses.
- Added tests for the revised behavior.
- Added coexistence tests for Grok and ChatGPT OAuth.

These changes have not been accepted as live-working behavior because the relevant tests and live OAuth flow were not run during this audit.

### Preferred direction

The preferred implementation is Hermes-style ChatGPT subscription OAuth/device authentication, if the Hermes source or an equivalent implementation is available.

The alternative is to reproduce the local-browser callback flow used by Codex/Prime Agent:

1. Open the ChatGPT subscription-login URL in a browser.
2. Complete authentication.
3. Capture the localhost callback URL containing the authorization data.
4. Paste or deliver that callback URL to the agent runtime.
5. Store the resulting token securely on the VPS.

The browser-callback approach is not currently implemented in Hierarchy.

## Agent-loop state

### Verified repository behavior

`vps-agent/src/hierarchy/runtime.py` defines:

```python
MAX_TOOL_STEPS = 12
```

The `_act` loop:

1. Sends the current conversation plus tool instructions to the configured model.
2. Expects a JSON tool call.
3. Executes the tool.
4. Appends the tool result to the conversation.
5. Repeats for up to 12 tool calls.
6. Returns: `I hit the tool-step limit. Check the computer screen and tell me how to continue.`

The tool protocol includes shell, read, write, list, fetch, message, and done.

The chat endpoint is synchronous for ordinary chat. The server has a job board for background work, but ordinary `rt.chat(...)` runs the full model/tool turn before returning the response.

### User-observed behavior

The agent behaved like a chat client rather than a fully autonomous agent:

- A request that should have led to repository work stopped at the 12-step limit.
- The response instructed the user to inspect the computer screen and continue.
- The computer screen exposed only an empty or minimal shell view, so it was not a usable recovery mechanism.
- The user had to send another message to continue the work.

This suggests the provider/runtime contract is not yet equivalent to a mature agent interface. The 12-step limit is explicitly present in the runtime, but the reason the model did not complete the task may also involve provider response format, tool-call parsing, missing persistent context, or the synchronous orchestration design.

### Memory and soul files

The current runtime stores one `instructions.md` file per bot and includes it as the system prompt.

It does not currently implement a Hermes-style layered memory/soul system. There is no verified support for durable `SOUL.md`, `MEMORY.md`, or equivalent files being automatically loaded into every turn.

A future agent-runtime task should define:

- Per-bot soul/personality instructions.
- Durable memory files.
- Conversation/session memory boundaries.
- Tool-result compaction.
- Explicit continuation/resume state.
- A configurable tool-step budget.
- Recovery when a provider emits malformed or non-JSON tool calls.

## Network incident diagnosis

This investigation was read-only and was performed by independent Luna audits.

### Verified findings

Hierarchy itself was not generating significant network load:

- `hierarchy.service` had zero restarts.
- It used approximately 0.1% CPU and roughly 22–26 MB RSS.
- Port `8765` had a listener but no connected clients during repeated samples.
- No active bot routines were found.
- The routine ticker runs approximately every 45 seconds but had no active work.
- The host was not under general CPU, memory, disk, or queue pressure.

The affected desktop-to-VPS Tailscale/SSH path showed:

- Approximately 33–60% packet loss in samples.
- High and unstable RTT.
- TCP retransmissions.
- Out-of-order packets.
- Duplicate/recovery traffic.
- Switching between a direct Tailscale path and the IAD DERP relay.

This is sufficient to explain typed characters accumulating locally and arriving in delayed bursts.

The VPS gateway's local path was healthy, so the VPS was not generally unable to communicate.

The user also verified:

- The same VPS was responsive from the phone throughout the day.
- The desktop is wired directly to its gateway.
- Another VPS from another provider is responsive from the same desktop.
- The provider's browser console is historically slow and should not be used as a control comparison for interactive responsiveness.

### Interpretation

The strongest current conclusion is that the immediate typing problem is specific to the desktop-to-this-VPS path, likely involving Tailscale endpoint/NAT state, routing/peering, or provider-side handling of this peer.

The abnormal DHCP/ARP broadcast activity seen on the VPS public interface is suspicious:

- A DHCP server offered an address from a different subnet than the VPS's configured address.
- Repeated offer/decline/discover/request traffic was observed.

This is provider-network evidence, but it has not been proven to cause the desktop-specific Tailscale lag.

No Hierarchy code change should be made solely to address this network incident.

## Build and validation log

Verified:

- The current tracked diff passed `git diff --check` before this document was added.
- The current source contains tests for OAuth coexistence, provider selection, and the recent ChatGPT OAuth request changes.
- `npm run typecheck` passed.
- The Python VPS-agent suite passed: 17/17 tests.
- `npm run build` passed after the current dirty changes. Its `db:migrate` step skipped the external migration because `DATABASE_URL` was unset and used the PGLite fallback.

Validation limitations and failures:

- `npm test` failed before executing the intended suite because its quoted glob was not expanded by the test runner.
- Direct Node test execution reported 5/10 passing; the five failures were environment/server-dependent.
- `npm run check:auth` could not complete in this environment because its required auth/deployment environment was unavailable.

Not run or not verified during this audit:

- Fresh Android APK build.
- Live Grok OAuth on the installed service.
- Live ChatGPT OAuth completion.
- End-to-end per-bot Grok/ChatGPT switching.
- End-to-end multi-step agent work using both providers.

Do not describe the current tree as release-ready until these checks pass.

## Migration plan for another VPS

1. Preserve the current working tree and review the dirty diff.
2. Commit only the intended source, tests, startup contract, project instructions, and both continuity documents: `docs/desktop-network-investigation-prompt.md` and `docs/2026-09-07-vps-migration-continuity.md`.
3. Push the reviewed commit to `origin/main`.
4. On the new VPS, clone `main`.
5. Install the service using:

   ```bash
   cd hierarchy/vps-agent
   sudo bash scripts/install-service.sh
   ```

6. Confirm:

   - `hierarchy.service` is enabled and active.
   - It listens on `0.0.0.0:8765`.
   - `GET /api/health` returns successfully.
   - The generated token is captured securely.
   - The VPS firewall/security group permits the intended access path.
   - Tailscale is connected and the `100.x.x.x` address is reachable.

7. Reconnect the Android client to the new VPS URL and token.
8. Create or restore the bot floor.
9. Reauthenticate Grok OAuth on the new VPS.
10. Test ChatGPT OAuth independently before assigning it to a bot.
11. Assign Grok to one bot and ChatGPT to another.
12. Send one simple chat request to each bot.
13. Send a multi-step task requiring shell/read/write tools.
14. Verify that tool calls appear in the computer state and that the agent completes without prematurely hitting the 12-step limit.
15. Only after acceptance, consider migrating histories, instructions, routines, and other `~/.hierarchy` state.

OAuth tokens in `~/.hierarchy/auth.json` must not be committed or copied casually. Reauthentication on the new VPS is preferred unless secure state migration is explicitly required.

## Immediate next tasks

Priority 1: run the desktop-side diagnostic prompt against both this VPS and a healthy comparison VPS.

Priority 2: inspect Hermes's ChatGPT OAuth/device-code implementation and compare its request headers, endpoints, polling semantics, token exchange, refresh behavior, and account headers with `vps-agent/src/hierarchy/oauth.py` and `llm.py`.

Priority 3: test the current dirty ChatGPT OAuth changes against the installed service. Capture the actual start, poll, exchange, and completion responses without exposing tokens.

Priority 4: repair the agent runtime contract so provider-backed models are treated as agent executors:

- Confirm supported tool-call format for each provider.
- Add robust parsing for native tool calls where available.
- Preserve tool-call state across turns.
- Make the tool-step limit configurable.
- Add explicit continuation/resume behavior.
- Improve the computer-screen state so it shows actionable progress and errors.
- Add durable soul/memory loading if Hermes-style behavior is desired.

Priority 5: migrate development to the healthier VPS after the reviewed commit is pushed and the new host passes service, provider, and multi-step-agent acceptance.
