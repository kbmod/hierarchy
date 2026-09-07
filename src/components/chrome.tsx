import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { ChevronLeft, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export function Screen({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("slide-in flex min-h-dvh flex-col bg-bg text-fg", className)}>
      {children}
    </div>
  );
}

export function TopBar({
  left,
  title,
  subtitle,
  right,
  onBack,
}: {
  left?: ReactNode;
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  onBack?: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-line bg-bg/90 px-3 py-2 pt-[max(0.5rem,env(safe-area-inset-top))] backdrop-blur-md">
      {onBack ? (
        <button
          type="button"
          onClick={onBack}
          className="grid size-11 place-items-center rounded-full text-fg"
          aria-label="Back"
        >
          <ChevronLeft className="size-6" strokeWidth={1.75} />
        </button>
      ) : (
        left
      )}
      <div className="min-w-0 flex-1">
        {title ? <div className="truncate text-[15px] font-semibold tracking-tight">{title}</div> : null}
        {subtitle ? <div className="truncate text-xs text-muted">{subtitle}</div> : null}
      </div>
      <div className="flex items-center gap-1">{right}</div>
    </header>
  );
}

export function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="grid size-11 place-items-center rounded-full text-fg transition-transform duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] active:scale-[0.96]"
    >
      {children}
    </button>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  type = "button",
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex h-12 w-full items-center justify-center rounded-[20px] bg-accent px-4 text-[15px] font-semibold text-accent-fg transition-transform duration-150 active:scale-[0.99] disabled:opacity-40",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  onClick,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex h-12 w-full items-center justify-center rounded-[20px] border border-line bg-surface px-4 text-[15px] font-medium text-fg",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}

export function TextField(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-12 w-full rounded-[16px] border border-line bg-surface px-4 text-[15px] text-fg outline-none placeholder:text-subtle focus:border-fg/30",
        props.className,
      )}
    />
  );
}

export function AreaField(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "min-h-28 w-full resize-none rounded-[20px] border border-line bg-surface px-4 py-3 text-[15px] text-fg outline-none placeholder:text-subtle focus:border-fg/30",
        props.className,
      )}
    />
  );
}

export function Banner({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "danger" }) {
  return (
    <div
      className={cn(
        "rounded-[16px] px-3 py-2 text-[13px] leading-snug",
        tone === "danger" ? "bg-danger/10 text-danger" : "bg-elevated text-muted",
      )}
    >
      {children}
    </div>
  );
}

export function BusyBar({ on }: { on: boolean }) {
  if (!on) return null;
  return (
    <div className="flex items-center gap-2 px-4 py-2 text-xs text-muted">
      <LoaderCircle className="size-3.5 animate-spin" />
      Working
    </div>
  );
}
