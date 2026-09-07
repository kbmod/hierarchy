export type AvatarSpec = {
  tone: "a" | "b" | "c" | "d" | "e" | "f" | "g" | "h";
  shape: "circle" | "drop" | "blob" | "triangle" | "squircle" | "diamond";
};

const TONES: AvatarSpec["tone"][] = ["a", "b", "c", "d", "e", "f", "g", "h"];
const SHAPES: AvatarSpec["shape"][] = ["circle", "drop", "blob", "triangle", "squircle", "diamond"];

const NAMED: Record<string, AvatarSpec> = {
  atlas: { tone: "a", shape: "circle" },
  forge: { tone: "e", shape: "squircle" },
  scout: { tone: "b", shape: "drop" },
  quill: { tone: "c", shape: "blob" },
};

function hash(input: string): number {
  let n = 0;
  for (let i = 0; i < input.length; i++) n = (n * 33 + input.charCodeAt(i)) >>> 0;
  return n;
}

export function avatarFor(name: string): AvatarSpec {
  const key = name.trim().toLowerCase();
  if (NAMED[key]) return NAMED[key];
  const h = hash(key || "bot");
  return { tone: TONES[h % TONES.length], shape: SHAPES[(h >> 3) % SHAPES.length] };
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "·";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
