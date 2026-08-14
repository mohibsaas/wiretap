import { Loader2, Play } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import {
  phaseIsActive,
  phaseLabel,
  type ScenarioProgress,
} from "@/lib/runProgress";
import { cn } from "@/lib/utils";

type Props = {
  row: ScenarioProgress;
  batchId: string;
  className?: string;
};

export function ScenarioProgressRow({ row, batchId, className }: Props) {
  const active = phaseIsActive(row.phase);
  const done = row.phase === "finished";
  const failed = row.phase === "failed";
  const label = phaseLabel(row.phase, row.turn);
  const detail =
    row.error ||
    (row.detail && row.detail !== "waiting for slot" ? row.detail : null);

  const body = (
    <div
      className={cn(
        "flex items-center gap-3.5 rounded-xl border border-border bg-card px-[18px] py-3.5 transition-colors",
        row.simulation_id &&
          "hover:border-[var(--wt-border-strong)] hover:bg-[var(--wt-section)]",
        className,
      )}
    >
      <div className="flex size-[34px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-primary">
        <Play className="size-4 fill-current" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14.5px] font-semibold">
          {row.scenario_name || row.scenario_id}
        </div>
        <div className="truncate text-[12.5px] text-muted-foreground">
          {detail || (active ? label : failed ? "Failed" : "Queued")}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2.5">
        {done && typeof row.passed === "boolean" && (
          <Badge
            variant={row.inconclusive ? "warn" : row.passed ? "pass" : "fail"}
          >
            {row.inconclusive ? "inconclusive" : row.passed ? "pass" : "fail"}
          </Badge>
        )}
        {failed && <Badge variant="fail">failed</Badge>}
        {active && (
          <span className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
            <span className="tabular-nums">{label}</span>
            <Loader2
              className="size-3.5 animate-spin text-primary/70"
              aria-hidden
            />
          </span>
        )}
      </div>
    </div>
  );

  if (row.simulation_id) {
    return (
      <Link
        to={`/evaluations/${batchId}/scenarios/${row.simulation_id}`}
        className="block"
      >
        {body}
      </Link>
    );
  }
  return body;
}
