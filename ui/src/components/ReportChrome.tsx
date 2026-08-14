import { Award, Lock } from "lucide-react";
import type { ReportBadge, ReportCategoryId, ReportStatus } from "@/lib/reports";
import { REPORT_CATEGORIES, badgeImageSrc, scoreBand } from "@/lib/reports";
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
  size = "sm",
}: {
  badge: ReportBadge;
  size?: "sm" | "lg";
}) {
  const wide = size === "lg";
  return (
    <img
      src={badgeImageSrc(badge)}
      alt={badge.met ? badge.name : `${badge.name} locked`}
      className={cn(
        "shrink-0 object-contain",
        wide ? "h-[186px] w-[186px]" : "h-[88px] w-[88px]",
      )}
    />
  );
}

export function ReportBadgeChip({ earned }: { earned: number }) {
  const on = earned > 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-[11px] py-1 text-[11.5px] font-medium",
        on
          ? "border border-primary bg-[var(--wt-green-100)] text-[var(--wt-green-700)]"
          : "border border-border bg-card text-[var(--wt-text-muted)]",
      )}
    >
      {on ? <Award className="size-3" /> : <Lock className="size-3" />}
      {on ? `${earned} badge${earned === 1 ? "" : "s"}` : "No badges"}
    </span>
  );
}
