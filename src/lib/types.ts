export type ProviderId = "stub" | "xai" | "openai" | "openrouter" | "grok" | "chatgpt";

export type VpsSlot = {
  id: string;
  label: string;
  url: string;
  token: string;
  role: "primary" | "backup";
};

export type AuthStatus = {
  active: ProviderId | string;
  keys: Record<string, { configured: boolean; model?: string; base_url?: string }>;
  oauth: Record<string, { configured: boolean; model?: string; expires_at?: number }>;
};

export type Bot = {
  id: string;
  name: string;
  job: string;
  description: string;
  preview: string;
  reports_to: string | null;
  provider?: string | null;
  model?: string | null;
  status?: string;
};

export type HistoryItem = {
  role: "user" | "assistant" | string;
  content: string;
};

export type ShellState = {
  status: string;
  cwd?: string;
  lines: string[];
  updated_at: number;
};

export type Job = {
  id: string;
  bot_id: string;
  kind: string;
  status: "working" | "done" | "error" | string;
  text: string;
  error?: string | null;
  created_at: number;
  updated_at: number;
};

export type Routine = {
  id: string;
  title: string;
  schedule: string;
  instruction: string;
  active: boolean;
};

export type Project = {
  id: string;
  name: string;
  outcome: string;
  lead_id: string;
  bot_ids: string[];
  status: string;
  created_at: number;
};

export type Group = {
  id: string;
  name: string;
  memberIds: string[];
  preview: string;
  updatedAt: number;
};

export type Screen =
  | { name: "home" }
  | { name: "chat"; botId: string }
  | { name: "group"; groupId: string }
  | { name: "computer"; botId?: string }
  | { name: "settings" }
  | { name: "setup" }
  | { name: "new-agent" }
  | { name: "new-group" }
  | { name: "project" }
  | { name: "search" }
  | { name: "profile"; botId: string }
  | { name: "oauth"; provider: "grok" | "chatgpt" }
  | { name: "install" }
  | { name: "backends" }
  | { name: "providers" };
