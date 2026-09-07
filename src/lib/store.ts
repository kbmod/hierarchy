import { create } from "zustand";
import type { Group, Screen, VpsSlot } from "./types";
import { uid } from "./utils";

type AppearanceMode = "system" | "light" | "dark";

type Persisted = {
  onboarded: boolean;
  appearance: AppearanceMode;
  vps: VpsSlot[];
  activeVpsId: string;
  drafts: Record<string, string>;
  pinned: string[];
  hidden: string[];
  groups: Group[];
};

type Store = Persisted & {
  stack: Screen[];
  busy: boolean;
  error: string | null;
  hydrate: () => void;
  persist: () => void;
  go: (screen: Screen) => void;
  back: () => void;
  resetTo: (screen: Screen) => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string | null) => void;
  completeOnboarding: () => void;
  setAppearance: (appearance: AppearanceMode) => void;
  upsertVps: (slot: VpsSlot) => void;
  addVps: () => string;
  removeVps: (id: string) => void;
  setActiveVps: (id: string) => void;
  setDraft: (id: string, text: string) => void;
  togglePin: (id: string) => void;
  hideConv: (id: string) => void;
  addGroup: (group: Group) => void;
  updateGroup: (id: string, patch: Partial<Group>) => void;
  activeVps: () => VpsSlot;
};

const KEY = "hierarchy.v1";

function demoSlots(): VpsSlot[] {
  return [
    {
      id: "vps-1",
      label: "Primary computer",
      url: "",
      token: "",
      role: "primary",
    },
    {
      id: "vps-2",
      label: "Backup computer",
      url: "",
      token: "",
      role: "backup",
    },
  ];
}

function load(): Persisted {
  const fallback: Persisted = {
    onboarded: false,
    appearance: "system",
    vps: demoSlots(),
    activeVpsId: "vps-1",
    drafts: {},
    pinned: [],
    hidden: [],
    groups: [],
  };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    return {
      ...fallback,
      ...parsed,
      vps: parsed.vps?.length ? parsed.vps : fallback.vps,
    };
  } catch {
    return fallback;
  }
}

export const useApp = create<Store>((set, get) => ({
  ...load(),
  stack: [{ name: "setup" }],
  busy: false,
  error: null,
  hydrate: () => {
    const data = load();
    set({
      ...data,
      stack: data.onboarded ? [{ name: "home" }] : [{ name: "setup" }],
    });
  },
  persist: () => {
    const s = get();
    const payload: Persisted = {
      onboarded: s.onboarded,
      appearance: s.appearance,
      vps: s.vps,
      activeVpsId: s.activeVpsId,
      drafts: s.drafts,
      pinned: s.pinned,
      hidden: s.hidden,
      groups: s.groups,
    };
    if (typeof window !== "undefined") {
      localStorage.setItem(KEY, JSON.stringify(payload));
    }
  },
  go: (screen) => set((s) => ({ stack: [...s.stack, screen], error: null })),
  back: () =>
    set((s) => ({
      stack: s.stack.length > 1 ? s.stack.slice(0, -1) : s.stack,
      error: null,
    })),
  resetTo: (screen) => set({ stack: [screen], error: null }),
  setBusy: (busy) => set({ busy }),
  setError: (error) => set({ error }),
  completeOnboarding: () => {
    set({ onboarded: true, stack: [{ name: "home" }] });
    get().persist();
  },
  setAppearance: (appearance) => {
    set({ appearance });
    get().persist();
  },
  upsertVps: (slot) => {
    set((s) => {
      const exists = s.vps.some((v) => v.id === slot.id);
      const vps = exists ? s.vps.map((v) => (v.id === slot.id ? slot : v)) : [...s.vps, slot];
      return { vps };
    });
    get().persist();
  },
  addVps: () => {
    const id = uid();
    const n = get().vps.length + 1;
    get().upsertVps({
      id,
      label: `Computer ${n}`,
      url: "",
      token: "",
      role: n === 1 ? "primary" : "backup",
    });
    return id;
  },
  removeVps: (id) => {
    set((s) => {
      const vps = s.vps.filter((v) => v.id !== id);
      const activeVpsId = s.activeVpsId === id ? (vps[0]?.id ?? "") : s.activeVpsId;
      return { vps, activeVpsId };
    });
    get().persist();
  },
  setActiveVps: (id) => {
    set({ activeVpsId: id });
    get().persist();
  },
  setDraft: (id, text) => {
    set((s) => ({ drafts: { ...s.drafts, [id]: text } }));
    get().persist();
  },
  togglePin: (id) => {
    set((s) => ({
      pinned: s.pinned.includes(id) ? s.pinned.filter((x) => x !== id) : [...s.pinned, id],
    }));
    get().persist();
  },
  hideConv: (id) => {
    set((s) => ({ hidden: s.hidden.includes(id) ? s.hidden : [...s.hidden, id] }));
    get().persist();
  },
  addGroup: (group) => {
    set((s) => ({ groups: [group, ...s.groups] }));
    get().persist();
  },
  updateGroup: (id, patch) => {
    set((s) => ({
      groups: s.groups.map((g) => (g.id === id ? { ...g, ...patch } : g)),
    }));
    get().persist();
  },
  activeVps: () => {
    const s = get();
    return s.vps.find((v) => v.id === s.activeVpsId) ?? s.vps[0] ?? demoSlots()[0];
  },
}));

export function newVpsId(): string {
  return uid();
}

export type { AppearanceMode };
