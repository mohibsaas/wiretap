import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Props = {
  title: string;
  subtitle?: string;
  meta?: string;
  action?: ReactNode;
  className?: string;
};

export function PageHeader({ title, subtitle, meta, action, className }: Props) {
  return (
    <header
      className={cn(
        "flex items-start justify-between gap-5",
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-baseline gap-2.5">
          <h1 className="text-[22px] font-semibold tracking-[-0.005em] text-foreground">
            {title}
          </h1>
          {meta ? (
            <span className="font-mono text-[13px] font-medium text-[var(--wt-text-muted)]">
              {meta}
            </span>
          ) : null}
        </div>
        {subtitle ? (
          <p className="max-w-2xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
            {subtitle}
          </p>
        ) : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </header>
  );
}
