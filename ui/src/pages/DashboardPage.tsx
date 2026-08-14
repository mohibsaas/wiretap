import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { cn } from "@/lib/utils";

const DANGER = "var(--wt-danger)";
const MUTED = "var(--wt-text-muted)";

const FLEET = {
  cleanRate: "81%",
  delta: "-3 pts vs last week",
  cleanCount: "141",
  flaggedCount: "33",
  flagRate: "19%",
  cleanFlex: 141,
  flaggedFlex: 33,
  agentsClean: "4 / 5",
  threshold: "under the 20% flag threshold",
  volume: "6 runs · 174 simulations · 5 agents this week",
};

/** Clean-rate series from the design prototype (W=620, L=34, TOP=14, BOT=168, lo=60, hi=100). */
const FLEET_CHART = {
  line: "M34.0 48.7 L150.0 60.2 L266.0 52.5 L382.0 71.8 L498.0 98.7 L614.0 87.2",
  area: "M34.0 48.7 L150.0 60.2 L266.0 52.5 L382.0 71.8 L498.0 98.7 L614.0 87.2 L614.0 168 L34.0 168 Z",
  grid: [
    { y: 14, ty: 18, label: "100%" },
    { y: 91, ty: 95, label: "80%" },
    { y: 168, ty: 172, label: "60%" },
  ],
  dots: [
    { cx: 34.0, cy: 48.7 },
    { cx: 150.0, cy: 60.2 },
    { cx: 266.0, cy: 52.5 },
    { cx: 382.0, cy: 71.8 },
    { cx: 498.0, cy: 98.7 },
    { cx: 614.0, cy: 87.2 },
  ],
  labels: [
    { value: "91%", when: "5 days", align: "left" as const },
    { value: "88%", when: "3 days", align: "center" as const },
    { value: "90%", when: "2 days", align: "center" as const },
    { value: "85%", when: "1 day", align: "center" as const },
    { value: "78%", when: "7 hours", align: "center" as const },
    { value: "81%", when: "2 hours", align: "right" as const },
  ],
};

type AgentRow = {
  name: string;
  meta: string;
  rate: string;
  count: string;
  hist: number[];
  worse: boolean;
  dangerRate: boolean;
};

const AGENTS: AgentRow[] = [
  {
    name: "Compliance",
    meta: "32 simulations · 3 days ago",
    rate: "38%",
    count: "12 / 32 flagged",
    hist: [24, 26, 29, 33, 38],
    worse: true,
    dangerRate: true,
  },
  {
    name: "Customer Support",
    meta: "50 simulations · 7 hours ago",
    rate: "22%",
    count: "11 / 50 flagged",
    hist: [26, 24, 25, 21, 22],
    worse: false,
    dangerRate: true,
  },
  {
    name: "Demo agent",
    meta: "50 simulations · 2 hours ago",
    rate: "14%",
    count: "7 / 50 flagged",
    hist: [22, 19, 18, 16, 14],
    worse: false,
    dangerRate: false,
  },
  {
    name: "Sales",
    meta: "18 simulations · 2 days ago",
    rate: "11%",
    count: "2 / 18 flagged",
    hist: [17, 15, 13, 11, 11],
    worse: false,
    dangerRate: false,
  },
  {
    name: "Onboarding",
    meta: "24 simulations · 1 day ago",
    rate: "4%",
    count: "1 / 24 flagged",
    hist: [9, 8, 6, 5, 4],
    worse: false,
    dangerRate: false,
  },
];

const CAT_TILES: Record<string, [string, string]> = {
  Emotional: ["#FEE9E9", "#B54444"],
  Linguistic: ["#EEEAF7", "#6B4EA8"],
  Adversarial: ["#F7EAEA", "#A73535"],
  Operational: ["#E6F0F7", "#2F6B9E"],
  Factual: ["#EFF3E6", "#5C7A2E"],
  Compliance: ["#F7F0E6", "#8A5B12"],
  Task: ["#E6EEE7", "#056938"],
};

const CATEGORIES = [
  { name: "Compliance", rate: "38%", count: "66 / 174", bar: 100 },
  { name: "Adversarial", rate: "29%", count: "50 / 174", bar: 76 },
  { name: "Emotional", rate: "21%", count: "37 / 174", bar: 55 },
  { name: "Factual", rate: "16%", count: "28 / 174", bar: 42 },
  { name: "Linguistic", rate: "13%", count: "23 / 174", bar: 34 },
  { name: "Operational", rate: "11%", count: "19 / 174", bar: 29 },
  { name: "Task", rate: "6%", count: "10 / 174", bar: 16 },
];

const REPORTS = [
  { name: "Manual test run", meta: "Demo agent", score: "86", ago: "2 hours ago", clean: false },
  { name: "dem run plan 01", meta: "Customer Support", score: "78", ago: "7 hours ago", clean: false },
  { name: "Onboarding flow QA", meta: "Onboarding", score: "96", ago: "1 day ago", clean: true },
  { name: "Refund flow regression", meta: "Sales", score: "91", ago: "2 days ago", clean: true },
  { name: "Reg pack sweep", meta: "Compliance", score: "69", ago: "3 days ago", clean: false },
];

function spark(vals: number[], w: number, h: number) {
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const pad = 2;
  return vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = pad + (1 - (v - min) / span) * (h - pad * 2);
    return { x, y };
  });
}

function SectionCard({
  title,
  meta,
  action,
  children,
  className,
  bodyClassName,
  headerClassName,
}: {
  title: string;
  meta?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  headerClassName?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border bg-card",
        className,
      )}
    >
      <div
        className={cn(
          "flex items-baseline justify-between gap-4 border-b border-border pb-[15px]",
          headerClassName,
        )}
      >
        <h3 className="m-0 text-[16.5px] font-semibold tracking-[-0.006em] text-foreground">
          {title}
        </h3>
        {action ?? (
          <span className="whitespace-nowrap text-xs text-[var(--wt-text-muted)]">
            {meta}
          </span>
        )}
      </div>
      <div className={bodyClassName}>{children}</div>
    </div>
  );
}

function FleetChart() {
  const last = FLEET_CHART.dots.length - 1;
  return (
    <div className="flex min-w-[380px] flex-1 basis-[460px] flex-col">
      <div className="flex items-baseline justify-between gap-4">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          Clean rate by run
        </div>
        <div className="text-xs text-[var(--wt-text-muted)]">last 6 runs</div>
      </div>
      <svg
        viewBox="0 0 620 190"
        width="100%"
        height="190"
        fill="none"
        preserveAspectRatio="none"
        className="mt-4 block"
        aria-hidden="true"
      >
        {FLEET_CHART.grid.map((g) => (
          <line
            key={g.label}
            x1="34"
            y1={g.y}
            x2="620"
            y2={g.y}
            stroke="var(--wt-border)"
            strokeWidth="1"
          />
        ))}
        {FLEET_CHART.grid.map((g) => (
          <text key={`t-${g.label}`} x="0" y={g.ty} fill="#A7A7A5" fontSize="11">
            {g.label}
          </text>
        ))}
        <path d={FLEET_CHART.area} fill="var(--wt-green-100)" />
        <path
          d={FLEET_CHART.line}
          stroke="var(--wt-green-600)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {FLEET_CHART.dots.map((d, i) => (
          <circle
            key={`${d.cx}-${d.cy}`}
            cx={d.cx}
            cy={d.cy}
            r={i === last ? 4.5 : 3}
            fill={i === last ? "var(--wt-green-600)" : "var(--wt-canvas)"}
            stroke="var(--wt-green-600)"
            strokeWidth="2"
          />
        ))}
      </svg>
      <div className="mt-2.5 flex justify-between gap-2 pl-[34px]">
        {FLEET_CHART.labels.map((l) => (
          <div
            key={l.when}
            className="min-w-0 flex-1"
            style={{ textAlign: l.align }}
          >
            <div className="font-mono text-xs font-semibold text-foreground">
              {l.value}
            </div>
            <div className="mt-[3px] text-[11px] text-[var(--wt-text-muted)]">
              {l.when}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DashboardPage() {
  return (
    <div className="flex flex-col pb-12">
      <PageHeader
        className="mb-6"
        title="Dashboard"
        meta="1 dashboard"
        subtitle="What the taps see, at a glance."
      />

      <SectionCard
        title="Fleet health"
        meta="this week"
        className="flex flex-col px-8 pt-[22px] pb-7"
        bodyClassName="mt-[26px] flex flex-wrap items-stretch gap-x-10 gap-y-8"
      >
        <div className="flex max-w-[340px] min-w-[280px] flex-1 basis-[300px] flex-col">
          <div className="m-0 flex items-end gap-3.5 whitespace-nowrap">
            <div className="font-mono text-[44px] leading-none font-semibold tracking-[-0.025em] text-foreground">
              {FLEET.cleanRate}
            </div>
            <div className="pb-[5px] text-[13px] text-muted-foreground">clean</div>
            <span className="inline-flex items-center gap-[5px] pb-1.5 text-xs font-medium whitespace-nowrap text-[var(--wt-danger)]">
              <svg width="9" height="9" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                <polygon points="6 11 1 2 11 2" />
              </svg>
              {FLEET.delta}
            </span>
          </div>
          <div className="mt-2.5 text-[12.5px] leading-normal text-pretty text-muted-foreground">
            Across every simulation on the record this week.
          </div>

          <div className="mt-[26px]">
            <div className="mb-3.5 flex h-2 gap-[3px]">
              <div
                className="rounded-full bg-[var(--wt-green-600)]"
                style={{ flex: FLEET.cleanFlex }}
              />
              <div
                className="rounded-full bg-[var(--wt-danger)]"
                style={{ flex: FLEET.flaggedFlex }}
              />
            </div>
            <div className="flex flex-col gap-[9px]">
              <div className="flex items-baseline gap-[9px]">
                <span className="size-[7px] shrink-0 rounded-full bg-[var(--wt-green-600)]" />
                <span className="font-mono text-sm font-semibold text-foreground">
                  {FLEET.cleanCount}
                </span>
                <span className="text-[12.5px] text-muted-foreground">clean</span>
              </div>
              <div className="flex items-baseline gap-[9px]">
                <span className="size-[7px] shrink-0 rounded-full bg-[var(--wt-danger)]" />
                <span className="font-mono text-sm font-semibold text-foreground">
                  {FLEET.flaggedCount}
                </span>
                <span className="text-[12.5px] text-muted-foreground">
                  flagged · {FLEET.flagRate}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-auto pt-[26px]">
            <div className="flex items-baseline gap-[9px]">
              <span className="font-mono text-sm font-semibold text-foreground">
                {FLEET.agentsClean}
              </span>
              <span className="text-[12.5px] text-muted-foreground">
                agents clean · {FLEET.threshold}
              </span>
            </div>
            <div className="mt-[9px] text-xs leading-normal text-[var(--wt-text-muted)]">
              {FLEET.volume}
            </div>
          </div>
        </div>

        <FleetChart />
      </SectionCard>

      <div className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(340px,1fr))] gap-6">
        <SectionCard
          title="Agents under tap"
          meta="worst first"
          className="px-[26px] pt-[22px] pb-3"
          bodyClassName="mt-3.5"
        >
          <div className="text-[12.5px] leading-normal text-muted-foreground">
            Flag rate across recent runs.
          </div>
          <div className="mt-3">
            {AGENTS.map((a, i) => {
              const pts = spark(a.hist, 62, 22);
              const last = pts[pts.length - 1];
              const color = a.worse ? DANGER : MUTED;
              return (
                <div
                  key={a.name}
                  className={cn(
                    "-mx-2.5 flex items-center gap-4 rounded-[10px] px-2.5 py-[13px] transition-colors hover:bg-[#F9F8F6]",
                    i > 0 && "border-t border-border",
                  )}
                >
                  <div className="min-w-[120px] flex-1">
                    <div className="truncate text-[13.5px] leading-snug font-semibold text-foreground">
                      {a.name}
                    </div>
                    <div className="mt-[3px] text-[11.5px] leading-snug text-[var(--wt-text-muted)]">
                      {a.meta}
                    </div>
                  </div>
                  <svg
                    width="66"
                    height="22"
                    viewBox="0 0 66 22"
                    fill="none"
                    className="shrink-0"
                    aria-hidden="true"
                  >
                    <polyline
                      points={pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}
                      stroke={color}
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <circle cx={last.x} cy={last.y} r="2" fill={color} />
                  </svg>
                  <div className="w-[82px] shrink-0 text-right">
                    <div
                      className="font-mono text-[17px] leading-none font-semibold tracking-[-0.01em]"
                      style={{ color: a.dangerRate ? DANGER : "var(--wt-text)" }}
                    >
                      {a.rate}
                    </div>
                    <div className="mt-[3px] text-[11.5px] text-[var(--wt-text-muted)]">
                      {a.count}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>

        <SectionCard
          title="Flags by category"
          meta="this week"
          className="px-[26px] pt-[22px] pb-6"
          bodyClassName="mt-3.5"
        >
          <div className="text-[12.5px] leading-normal text-muted-foreground">
            Flag rate per category across the last 6 runs.
          </div>
          <div className="mt-3 flex flex-col gap-0.5">
            {CATEGORIES.map((c) => {
              const [bg, fg] = CAT_TILES[c.name];
              return (
                <div key={c.name} className="flex min-w-0 items-center gap-3 py-2">
                  <span
                    className="inline-flex w-[92px] shrink-0 items-center justify-center rounded-full px-0 py-1 text-[11.5px] font-medium whitespace-nowrap"
                    style={{ background: bg, color: fg }}
                  >
                    {c.name}
                  </span>
                  <div
                    className="h-1.5 min-w-12 flex-1 rounded-full"
                    style={{ background: bg }}
                  >
                    <div
                      className="h-1.5 rounded-full"
                      style={{ background: fg, width: `${c.bar}%` }}
                    />
                  </div>
                  <span className="w-[38px] shrink-0 text-right font-mono text-[13px] font-semibold text-foreground">
                    {c.rate}
                  </span>
                  <span className="w-[60px] shrink-0 text-right text-[11.5px] whitespace-nowrap text-[var(--wt-text-muted)]">
                    {c.count}
                  </span>
                </div>
              );
            })}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Recent reports"
        className="mt-6 px-[26px] pt-[22px] pb-3.5"
        headerClassName="pb-[13px]"
        bodyClassName="mt-3.5"
        action={
          <Link
            to="/reports"
            className="inline-flex items-center gap-[7px] rounded-full px-3 py-2 text-[12.5px] font-medium text-muted-foreground no-underline transition-colors hover:bg-[#F9F8F6] hover:text-foreground"
          >
            All reports
            <ArrowRight className="size-[13px]" strokeWidth={1.9} />
          </Link>
        }
      >
        <div className="text-[12.5px] leading-normal text-muted-foreground">
          One per run, newest first.
        </div>
        <div className="mt-2">
          {REPORTS.map((r, i) => (
            <div
              key={r.name}
              className={cn(
                "-mx-2.5 flex items-center gap-4 rounded-[10px] px-2.5 py-[13px] transition-colors hover:bg-[#F9F8F6]",
                i > 0 && "border-t border-border",
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] leading-snug font-semibold text-foreground">
                  {r.name}
                </div>
                <div className="mt-[3px] text-[11.5px] leading-snug text-[var(--wt-text-muted)]">
                  {r.meta}
                </div>
              </div>
              <span
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-[11px] py-[3px] text-xs font-semibold",
                  r.clean
                    ? "border-[var(--wt-green-600)] bg-[var(--wt-green-100)] text-[var(--wt-green-700)]"
                    : "border-[var(--wt-danger)] bg-card text-[var(--wt-danger)]",
                )}
              >
                <span
                  className="inline-block size-1.5 shrink-0 rounded-full"
                  style={{
                    background: r.clean ? "var(--wt-green-600)" : DANGER,
                  }}
                />
                {r.clean ? "Clean" : "Flagged"}
              </span>
              <div className="w-11 shrink-0 text-right font-mono text-[15px] font-semibold text-foreground">
                {r.score}
              </div>
              <div className="w-[88px] shrink-0 text-right text-xs text-[var(--wt-text-muted)]">
                {r.ago}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
