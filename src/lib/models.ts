import type { ProviderId } from "./types";

export const PROVIDER_OPTIONS: { id: ProviderId | ""; label: string }[] = [
  { id: "", label: "Default (VPS active)" },
  { id: "stub", label: "Stub (offline)" },
  { id: "grok", label: "Grok OAuth" },
  { id: "xai", label: "xAI API key" },
  { id: "chatgpt", label: "ChatGPT OAuth" },
  { id: "openai", label: "OpenAI API key" },
  { id: "openrouter", label: "OpenRouter" },
];

export const PROVIDER_MODELS: Record<string, string[]> = {
  grok: ["grok-4.6", "grok-4.5", "grok-3"],
  xai: ["grok-4.6", "grok-4.5", "grok-3"],
  chatgpt: ["gpt-5.4", "gpt-5"],
  openai: ["gpt-4.1", "gpt-4o", "o3"],
  openrouter: ["openai/gpt-4.1-mini", "x-ai/grok-4.5", "anthropic/claude-sonnet-4"],
};

export function modelsFor(provider: string): string[] {
  return PROVIDER_MODELS[provider] || [];
}

export function defaultModel(provider: string): string {
  return modelsFor(provider)[0] || "";
}

export function providerLabel(id: string | null | undefined): string {
  if (!id) return "Default";
  return PROVIDER_OPTIONS.find((p) => p.id === id)?.label || id;
}
