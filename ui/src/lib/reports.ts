/** Report aggregation: one evaluation run → one scored report. */

import type {
  AgentRow,
  EvaluationRun,
  RunAdvice,
  Simulation,
  SuiteDetail,
  SuiteSummary,
} from "@/lib/api";
import { parseTime, simulationVerdict } from "@/lib/format";

export const CLEAN_THRESHOLD = 90;

export const REPORT_CATEGORIES = [
  { id: "emotional", label: "Emotional" },
  { id: "linguistic", label: "Linguistic" },
  { id: "adversarial", label: "Adversarial" },
  { id: "operational", label: "Operational" },
  { id: "factual", label: "Factual" },
  { id: "compliance", label: "Compliance" },
  { id: "task", label: "Task" },
] as const;

export type ReportCategoryId = (typeof REPORT_CATEGORIES)[number]["id"];

export type ReportStatus = "Clean" | "Flagged";

export const BADGE_NAMES: Record<ReportCategoryId, string> = {
  emotional: "Calm Under Fire",
  linguistic: "Clear Listener",
  adversarial: "Unbreakable",
  operational: "Interruption Handler",
  factual: "Hallucination Free",
  compliance: "Regulation Ready",
  task: "Task Keeper",
};

export type BadgeDef = {
  id: ReportCategoryId;
  name: string;
  cat: ReportCategoryId;
  crit: string;
};

export const BADGE_DEFS: BadgeDef[] = REPORT_CATEGORIES.map((c) => ({
  id: c.id,
  name: BADGE_NAMES[c.id],
  cat: c.id,
  crit: `Pass every ${c.label} simulation in this run.`,
}));

export type ReportBadge = BadgeDef & {
  value: number | null;
  locked: boolean;
  met: boolean;
  passedCount: number;
  testCount: number;
};

export function badgeImageSrc(badge: Pick<ReportBadge, "met" | "cat">): string {
  return badge.met ? `/badges/${badge.cat}.png` : "/badges/locked.png";
}

export type ScenarioMeta = {
  category?: string | null;
  success_criteria?: string | null;
  name?: string;
};

export type ScenarioIndex = Record<string, ScenarioMeta>;

export type ReportSimRow = {
  simulation: Simulation;
  categoryId: ReportCategoryId | null;
  categoryLabel: string;
  expected: string;
  score: number | null;
  flagged: boolean;
  fix: string;
};

export type ReportView = {
  batchId: string;
  name: string;
  suiteId: string;
  agent: string;
  hash: string;
  createdAt?: string;
  overall: number | null;
  status: ReportStatus;
  full: boolean;
  scores: Record<ReportCategoryId, number | null>;
  covered: ReportCategoryId[];
  missing: ReportCategoryId[];
  simCount: number;
  flaggedCount: number;
  passedCount: number;
  badges: ReportBadge[];
  issued: string;
  expires: string;
  period: string;
  rows: ReportSimRow[];
};

const LABEL_BY_ID: Record<ReportCategoryId, string> = Object.fromEntries(
  REPORT_CATEGORIES.map((c) => [c.id, c.label]),
) as Record<ReportCategoryId, string>;

const ID_BY_KEY: Record<string, ReportCategoryId> = Object.fromEntries(
  REPORT_CATEGORIES.flatMap((c) => [
    [c.id, c.id],
    [c.label.toLowerCase(), c.id],
  ]),
) as Record<string, ReportCategoryId>;

export function normalizeCategory(
  raw?: string | null,
): { id: ReportCategoryId; label: string } | null {
  const key = String(raw || "")
    .trim()
    .toLowerCase();
  if (!key) return null;
  const id = ID_BY_KEY[key];
  if (!id) return null;
  return { id, label: LABEL_BY_ID[id] };
}

export function reportHash(batchId: string): string {
  const hex = batchId.replace(/[^a-fA-F0-9]/g, "");
  return (hex || batchId).slice(0, 6).toLowerCase();
}

export function simScorePct(sim: Simulation): number | null {
  return simulationVerdict(sim).pct;
}

export function scoreBand(value: number | null): "high" | "mid" | "low" | "empty" {
  if (value == null) return "empty";
  if (value >= 85) return "high";
  if (value >= 70) return "mid";
  return "low";
}

export function indexSuiteScenarios(suite: SuiteDetail | null | undefined): ScenarioIndex {
  const out: ScenarioIndex = {};
  for (const sc of suite?.scenarios || []) {
    out[sc.id] = {
      category: sc.category,
      success_criteria: sc.success_criteria,
      name: sc.name,
    };
  }
  return out;
}

export function simsForRun(run: EvaluationRun, allSims: Simulation[]): Simulation[] {
  if (run.simulations && run.simulations.length > 0) return run.simulations;
  const ids = new Set(run.simulation_ids || []);
  return allSims.filter(
    (s) => s.batch_id === run.batch_id || ids.has(s.simulation_id),
  );
}

export function resolveAgentName(
  run: EvaluationRun,
  agents: AgentRow[],
  suite?: SuiteDetail | SuiteSummary | null,
  sims: Simulation[] = [],
): string {
  const match = agents.find(
    (a) =>
      a.suite === run.suite_id ||
      (suite && "agent" in suite && a.agent_id && a.agent_id === suite.agent?.agent_id),
  );
  if (match?.name) return match.name;
  if (match?.agent_id) return match.agent_id;
  if (suite && "agent" in suite && suite.agent?.platform) return suite.agent.platform;
  if (suite && "platform" in suite && suite.platform) return suite.platform;
  const fromSim = sims[0]?.meta?.platform;
  if (typeof fromSim === "string" && fromSim) return fromSim;
  return "Agent";
}

function categoryForSim(
  sim: Simulation,
  index: ScenarioIndex,
): { id: ReportCategoryId; label: string } | null {
  const fromSuite = index[sim.scenario_id]?.category;
  const fromMeta =
    typeof sim.meta?.category === "string" ? sim.meta.category : null;
  return normalizeCategory(fromSuite || fromMeta);
}

function suggestedFix(sim: Simulation, advice: RunAdvice | null | undefined): string {
  const fromJudge = (sim.judge?.suggestions || []).find((s) => s.trim());
  if (fromJudge) return fromJudge.trim();
  const finding = (advice?.findings || []).find((f) =>
    (f.affected_scenarios || []).includes(sim.scenario_id),
  );
  const text = finding?.recommendation || finding?.title || "";
  return text.trim();
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return Math.round(values.reduce((a, b) => a + b, 0) / values.length);
}

function formatIssued(ts?: string | null): string {
  const ms = parseTime(ts);
  if (ms == null) return "—";
  return new Date(ms).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatExpires(ts?: string | null): string {
  const ms = parseTime(ts);
  if (ms == null) return "—";
  const d = new Date(ms);
  d.setDate(d.getDate() + 90);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function seasonPeriod(ts?: string | null): string {
  const ms = parseTime(ts) ?? Date.now();
  const d = new Date(ms);
  const month = d.getMonth();
  const year = d.getFullYear();
  if (month >= 2 && month <= 4) return `Spring ${year}`;
  if (month >= 5 && month <= 7) return `Summer ${year}`;
  if (month >= 8 && month <= 10) return `Fall ${year}`;
  const winterYear = month === 11 ? year : year - 1;
  return `Winter ${winterYear}`;
}

export function buildReport(opts: {
  run: EvaluationRun;
  sims: Simulation[];
  index: ScenarioIndex;
  agent: string;
  advice?: RunAdvice | null;
}): ReportView {
  const { run, index, agent } = opts;
  const sims = [...opts.sims].sort((a, b) =>
    String(a.created_at || "").localeCompare(String(b.created_at || "")),
  );
  const advice = opts.advice ?? run.advice ?? null;

  const scores = Object.fromEntries(
    REPORT_CATEGORIES.map((c) => [c.id, null as number | null]),
  ) as Record<ReportCategoryId, number | null>;
  const buckets: Record<ReportCategoryId, number[]> = Object.fromEntries(
    REPORT_CATEGORIES.map((c) => [c.id, [] as number[]]),
  ) as Record<ReportCategoryId, number[]>;

  const rows: ReportSimRow[] = sims.map((sim) => {
    const cat = categoryForSim(sim, index);
    const score = simScorePct(sim);
    if (cat && score != null) buckets[cat.id].push(score);
    const verdict = simulationVerdict(sim);
    const expected = index[sim.scenario_id]?.success_criteria?.trim() || "—";
    return {
      simulation: sim,
      categoryId: cat?.id ?? null,
      categoryLabel: cat?.label || "Other",
      expected,
      score,
      flagged: verdict.label !== "Passed",
      fix: suggestedFix(sim, advice),
    };
  });

  for (const c of REPORT_CATEGORIES) {
    scores[c.id] = mean(buckets[c.id]);
  }

  const covered = REPORT_CATEGORIES.filter((c) => scores[c.id] != null).map(
    (c) => c.id,
  );
  const missing = REPORT_CATEGORIES.filter((c) => scores[c.id] == null).map(
    (c) => c.id,
  );
  const overall = mean(covered.map((id) => scores[id] as number));
  const full = covered.length === REPORT_CATEGORIES.length;
  const flaggedCount = rows.filter((r) => r.flagged).length;

  const badges: ReportBadge[] = BADGE_DEFS.map((b) => {
    const tests = rows.filter((r) => r.categoryId === b.cat);
    const passed = tests.filter((r) => !r.flagged).length;
    const met = tests.length > 0 && passed === tests.length;
    return {
      ...b,
      value: scores[b.cat],
      locked: !met,
      met,
      passedCount: passed,
      testCount: tests.length,
    };
  });

  return {
    batchId: run.batch_id,
    name: run.suite_id || "Report",
    suiteId: run.suite_id || "",
    agent,
    hash: reportHash(run.batch_id),
    createdAt: run.created_at,
    overall,
    status: overall != null && overall >= CLEAN_THRESHOLD ? "Clean" : "Flagged",
    full,
    scores,
    covered,
    missing,
    simCount: rows.length || run.total || 0,
    flaggedCount,
    passedCount: Math.max(0, (rows.length || run.total || 0) - flaggedCount),
    badges,
    issued: formatIssued(run.created_at),
    expires: formatExpires(run.created_at),
    period: seasonPeriod(run.created_at),
    rows,
  };
}

export function reportMetaLine(report: ReportView, simCount = report.simCount): string {
  return `${report.suiteId || "suite"} · ${report.agent} · ${simCount} simulation${
    simCount === 1 ? "" : "s"
  } · ℣-${report.hash}`;
}

export function categoryLabel(id: ReportCategoryId): string {
  return LABEL_BY_ID[id];
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadText(filename: string, body: string, type: string): void {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadBadgePng(badge: ReportBadge): Promise<void> {
  if (!badge.met) return;
  const blob = await fetch(badgeImageSrc(badge)).then((r) => {
    if (!r.ok) throw new Error("Could not load the badge image.");
    return r.blob();
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `wiretap-badge-${badge.cat}.png`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Compose earned category shields into one PNG — display art only, no secrets. */
export async function downloadBadgePack(report: ReportView): Promise<void> {
  const earned = report.badges.filter((b) => b.met);
  if (earned.length === 0) return;
  if (earned.length === 1) {
    await downloadBadgePng(earned[0]);
    return;
  }
  const size = 360;
  const gap = 16;
  const images = await Promise.all(
    earned.map((b) => loadImage(badgeImageSrc(b))),
  );
  const canvas = document.createElement("canvas");
  canvas.width = earned.length * size + (earned.length - 1) * gap;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not compose the badge pack.");
  images.forEach((img, i) => {
    ctx.drawImage(img, i * (size + gap), 0, size, size);
  });
  await new Promise<void>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("Could not compose the badge pack."));
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `wiretap-badges-${report.hash}.png`;
      a.click();
      URL.revokeObjectURL(url);
      resolve();
    }, "image/png");
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Could not load a badge image."));
    img.src = src;
  });
}
