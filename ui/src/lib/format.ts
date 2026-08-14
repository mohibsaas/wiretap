/** Format helpers for simulation / evaluation UI. */

export function parseTime(value?: string | null): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

export function formatDuration(ms: number | null): string {
  if (ms == null || ms < 0) return "—";
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm ? `${h}h ${rm}m` : `${h}h`;
}

export function formatRelative(value?: string | null): string {
  const ms = parseTime(value);
  if (ms == null) return "—";
  const diff = Date.now() - ms;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 48) return `${hr} hour${hr === 1 ? "" : "s"} ago`;
  const day = Math.round(hr / 24);
  return `${day} day${day === 1 ? "" : "s"} ago`;
}

export function runDuration(
  createdAt?: string | null,
  finishedAt?: string | null,
): string {
  const start = parseTime(createdAt);
  const end = parseTime(finishedAt) ?? (start != null ? Date.now() : null);
  if (start == null || end == null) return "—";
  return formatDuration(end - start);
}

export function runVerdict(passed: number, failed: number, total: number) {
  if (total <= 0) return { label: "empty", variant: "muted" as const };
  if (failed === 0) return { label: "Passed", variant: "pass" as const };
  if (passed === 0) return { label: "Failed", variant: "fail" as const };
  return { label: "Mixed", variant: "warn" as const };
}

/** Pass rate as a whole-number percent string, or null when total is empty. */
export function passRatePercent(passed: number, total: number): string | null {
  if (total <= 0) return null;
  return `${Math.round((passed / total) * 100)}%`;
}

export function statusTone(status?: string | null) {
  const s = (status || "").toLowerCase();
  if (s === "completed" || s === "passed" || s === "pass") return "pass" as const;
  if (s === "failed" || s === "error" || s === "fail") return "fail" as const;
  if (
    s === "running" ||
    s === "pending" ||
    s === "started" ||
    s === "partial" ||
    s === "inconclusive" ||
    s === "warn"
  )
    return "warn" as const;
  return "muted" as const;
}

/** Goal-match bands for a single simulation (fail / partial / pass). */
export type SimVerdict = {
  label: "Passed" | "Partial" | "Failed" | "Inconclusive";
  variant: "pass" | "warn" | "fail";
  pct: number | null;
};

export function simulationVerdict(sim: {
  passed?: boolean;
  judge?: {
    score?: number | null;
    verdict?: string | null;
    fail_below?: number | null;
    pass_at?: number | null;
  };
  meta?: Record<string, unknown> | null;
}): SimVerdict {
  if (sim.meta?.inconclusive) {
    return { label: "Inconclusive", variant: "warn", pct: null };
  }
  const score =
    typeof sim.judge?.score === "number"
      ? sim.judge.score
      : typeof sim.meta?.goal_match_pct === "number"
        ? Number(sim.meta.goal_match_pct) / 100
        : null;
  const pct =
    score != null && Number.isFinite(score)
      ? Math.round(Math.min(1, Math.max(0, score)) * 100)
      : typeof sim.meta?.goal_match_pct === "number"
        ? Math.round(Number(sim.meta.goal_match_pct))
        : null;

  const raw = String(sim.judge?.verdict || sim.meta?.verdict || "").toLowerCase();
  if (raw === "pass") {
    return { label: "Passed", variant: "pass", pct };
  }
  if (raw === "partial") {
    return { label: "Partial", variant: "warn", pct };
  }
  if (raw === "fail") {
    return { label: "Failed", variant: "fail", pct };
  }
  // Infer from score when verdict missing (older artifacts).
  if (score != null) {
    const failBelow =
      typeof sim.judge?.fail_below === "number" ? sim.judge.fail_below : 0.5;
    const passAt = typeof sim.judge?.pass_at === "number" ? sim.judge.pass_at : 0.7;
    if (score >= passAt) return { label: "Passed", variant: "pass", pct };
    if (score >= failBelow) return { label: "Partial", variant: "warn", pct };
    return { label: "Failed", variant: "fail", pct };
  }
  if (sim.passed) {
    return { label: "Passed", variant: "pass", pct };
  }
  return { label: "Failed", variant: "fail", pct };
}

export function formatGoalPct(score: number | null | undefined): string {
  if (score == null || !Number.isFinite(score)) return "—";
  const n = score > 1 && score <= 100 ? score : score * 100;
  return `${Math.round(n)}%`;
}
