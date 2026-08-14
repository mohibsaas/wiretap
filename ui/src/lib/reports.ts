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

export type BadgeDef = {
  id: string;
  name: string;
  cat: ReportCategoryId | null;
  min: number;
  crit: string;
};

export const BADGE_DEFS: BadgeDef[] = [
  {
    id: "b1",
    name: "Voice Agent Verified",
    cat: null,
    min: 70,
    crit: "Overall 70 or higher, all 7 categories",
  },
  {
    id: "b2",
    name: "High Performer",
    cat: null,
    min: 85,
    crit: "Overall 85 or higher, all 7 categories",
  },
  {
    id: "b3",
    name: "Compliance Ready",
    cat: "compliance",
    min: 90,
    crit: "Compliance 90 or higher, all 7 categories",
  },
  {
    id: "b4",
    name: "Adversarial Resilient",
    cat: "adversarial",
    min: 85,
    crit: "Adversarial 85 or higher, all 7 categories",
  },
];

export type ReportBadge = BadgeDef & {
  value: number | null;
  locked: boolean;
  met: boolean;
};

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
    const value = b.cat ? scores[b.cat] : overall;
    return {
      ...b,
      value,
      locked: !full,
      met: full && value != null && value >= b.min,
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

/** Client-side SVG pack of earned badges — no secrets, display scores only. */
export function badgePackSvg(report: ReportView): string {
  const earned = report.badges.filter((b) => b.met);
  const cards = earned.length ? earned : report.badges;
  const w = 220;
  const h = 260;
  const gap = 16;
  const width = cards.length * w + (cards.length - 1) * gap + 40;
  const height = h + 40;
  const plates = cards
    .map((b, i) => {
      const x = 20 + i * (w + gap);
      const on = b.met;
      const fill = on ? "#056938" : "#E4E3DF";
      const name = escapeXml(b.name);
      const value = b.locked || b.value == null ? "—" : String(b.value);
      return `<g transform="translate(${x},20)">
  <rect width="${w}" height="${h}" rx="16" fill="${on ? "#FFFFFF" : "#F9F8F6"}" stroke="${on ? "#056938" : "#D8D6D1"}"/>
  <rect width="${w}" height="36" rx="16" fill="${fill}"/>
  <rect y="20" width="${w}" height="16" fill="${fill}"/>
  <text x="${w / 2}" y="24" text-anchor="middle" fill="${on ? "#FFFFFF" : "#8A8984"}" font-family="system-ui,sans-serif" font-size="11" font-weight="600" letter-spacing="2">WIRETAP</text>
  <text x="${w / 2}" y="110" text-anchor="middle" fill="${on ? "#056938" : "#8A8984"}" font-family="system-ui,sans-serif" font-size="16" font-weight="600">${name}</text>
  <text x="${w / 2}" y="160" text-anchor="middle" fill="#292927" font-family="ui-monospace,monospace" font-size="36" font-weight="600">${value}</text>
  <text x="${w / 2}" y="190" text-anchor="middle" fill="#8A8984" font-family="system-ui,sans-serif" font-size="11" font-weight="600" letter-spacing="1.5">${escapeXml(report.period.toUpperCase())}</text>
</g>`;
    })
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  ${plates}
</svg>
`;
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
