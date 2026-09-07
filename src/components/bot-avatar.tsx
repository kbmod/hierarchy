import { avatarFor, initials } from "@/lib/avatars";
import { cn } from "@/lib/utils";

export function BotAvatar({
  name,
  size = "md",
  stacked = false,
}: {
  name: string;
  size?: "sm" | "md" | "lg" | "xl";
  stacked?: boolean;
}) {
  const spec = avatarFor(name);
  const dim =
    size === "sm" ? "size-9" : size === "lg" ? "size-16" : size === "xl" ? "size-20" : "size-12";
  return (
    <div
      className={cn(
        "relative grid place-items-center overflow-hidden text-white",
        dim,
        `avatar-tone-${spec.tone}`,
        `avatar-shape-${spec.shape}`,
        stacked && "ring-2 ring-bg",
      )}
      aria-hidden
    >
      <span className="text-[0.7em] font-semibold tracking-tight">{initials(name)}</span>
    </div>
  );
}
