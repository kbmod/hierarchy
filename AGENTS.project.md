# Project direction: Hermes-derived autonomous bot runtime

Hierarchy is intended to become a faithful clone of Grok Bot behavior. The
canonical architectural reference is Hermes Agent's actual bot/gateway mode
and its verified source and entrypoint, not an inferred protocol or a
chat-client integration.

Binding requirements for all future work:

- The primary runtime must be the Hermes-derived autonomous bot runtime. ACP,
  Codex app-server, a one-message/one-response chat wrapper, and a custom
  short-step loop are not acceptable primary architectures.
- Grok OAuth and ChatGPT subscription OAuth must both run through the same
  Hermes-derived autonomous bot runtime, with explicit per-bot provider and
  model selection and independent credentials.
- The runtime must support persistent long-running tool work, specialist bot
  creation, delegation, bot-to-bot messaging, durable `SOUL.md`/memory state,
  resume after interruption or restart, meaningful progress, and actionable
  approval requests in the client.
- Before proposing or implementing an architecture, identify the actual
  Hermes bot/gateway entrypoint and source it is based on, pin or record the
  source revision, and demonstrate how the proposed adapter maps to that
  implementation. Do not infer Hermes behavior from endpoint names, OAuth
  URLs, or a superficially similar client flow.
- Existing Hierarchy state and APIs should be migrated compatibly where safe,
  but compatibility code must not silently become the primary runtime.

The checked-in `start.md` procedure and this project directive both apply;
preserve their safety, review, and validation requirements.
