import { Award, Lock } from "lucide-react";
import type { ReportBadge, ReportCategoryId, ReportStatus } from "@/lib/reports";
import { REPORT_CATEGORIES, scoreBand } from "@/lib/reports";
import { cn } from "@/lib/utils";

export function ReportStatusPill({ status }: { status: ReportStatus }) {
  const clean = status === "Clean";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-[11px] py-[3px] text-xs font-semibold",
        clean
          ? "border border-primary bg-[var(--wt-green-100)] text-[var(--wt-green-700)]"
          : "border border-[var(--wt-danger)] bg-card text-[var(--wt-danger)]",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          clean ? "bg-primary" : "bg-[var(--wt-danger)]",
        )}
      />
      {status}
    </span>
  );
}

export function ReportScorePlate({
  score,
  clean,
}: {
  score: number | null;
  clean: boolean;
}) {
  return (
    <div
      className={cn(
        "flex size-14 shrink-0 flex-col items-center justify-center rounded-[13px] border",
        clean
          ? "border-primary bg-[var(--wt-green-100)]"
          : "border-border bg-[var(--wt-section)]",
      )}
    >
      <span
        className={cn(
          "font-mono text-[19px] font-semibold leading-none tracking-[-0.02em]",
          clean ? "text-[var(--wt-green-700)]" : "text-foreground",
        )}
      >
        {score == null ? "—" : score}
      </span>
      <span className="mt-0.5 text-[9px] font-semibold tracking-[0.07em] text-[var(--wt-text-muted)] uppercase">
        score
      </span>
    </div>
  );
}

export function CategorySpark({
  scores,
}: {
  scores: Record<ReportCategoryId, number | null>;
}) {
  return (
    <div className="flex items-end gap-[3px]">
      {REPORT_CATEGORIES.map((c) => {
        const v = scores[c.id];
        const band = scoreBand(v);
        return (
          <span
            key={c.id}
            title={v == null ? `${c.label} · not covered` : `${c.label} · ${v}`}
            className={cn(
              "inline-block w-[5px] rounded-[3px]",
              v == null ? "h-2.5 bg-border" : "h-5",
              band === "high" && "bg-[var(--wt-green-600)]",
              band === "mid" && "bg-[rgba(5,105,56,0.40)]",
              band === "low" && "bg-[var(--wt-danger)]",
            )}
          />
        );
      })}
    </div>
  );
}

export function ReportBadgePlate({
  badge,
  period,
  size = "sm",
}: {
  badge: ReportBadge;
  period: string;
  size?: "sm" | "lg";
}) {
  const on = badge.met;
  const wide = size === "lg";
  return (
    <div
      className={cn(
        "flex shrink-0 flex-col overflow-hidden",
        wide ? "h-[186px] w-[148px] rounded-2xl" : "h-[110px] w-[88px] rounded-xl",
        on
          ? "border border-primary bg-white"
          : "border border-border bg-[var(--wt-section)] opacity-70",
      )}
    >
      <div
        className={cn(
          "shrink-0 text-center font-semibold tracking-[0.16em]",
          wide ? "py-[9px] text-[9.5px]" : "py-1.5 text-[8px]",
          on
            ? "bg-[var(--wt-green-600)] text-white"
            : "bg-border text-[var(--wt-text-muted)]",
        )}
      >
        WIRETAP
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-1 px-1.5 py-2 text-center">
        <div
          className={cn(
            "font-semibold leading-tight",
            wide ? "text-sm" : "text-[9.5px]",
            on ? "text-[var(--wt-green-700)]" : "text-muted-foreground",
          )}
        >
          {badge.name}
        </div>
        <div
          className={cn(
            "font-mono font-semibold leading-none tracking-[-0.02em]",
            wide ? "text-[30px]" : "text-[17px]",
            on ? "text-foreground" : "text-[var(--wt-text-muted)]",
          )}
        >
          {badge.locked || badge.value == null ? "—" : badge.value}
        </div>
        <div className="text-[8px] font-semibold tracking-[0.09em] text-[var(--wt-text-muted)] uppercase">
          {period}
        </div>
      </div>
    </div>
  );
}

export function ReportBadgeChip({
  full,
  earned,
}: {
  full: boolean;
  earned: number;
}) {
  const on = full && earned > 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-[11px] py-1 text-[11.5px] font-medium",
        on
          ? "border border-primary bg-[var(--wt-green-100)] text-[var(--wt-green-700)]"
          : "border border-border bg-card text-[var(--wt-text-muted)]",
      )}
    >
      {full ? (
        <Award className="size-3" />
      ) : (
        <Lock className="size-3" />
      )}
      {full
        ? `${earned} badge${earned === 1 ? "" : "s"}`
        : "Badges locked"}
    </span>
  );
}
