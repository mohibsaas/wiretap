import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, Bot, Layers, LineChart, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  client,
  type AgentRow,
  type EvaluationRun,
  type Simulation,
  type SuiteSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(ts: number): number {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function dayLabel(ts: number): string {
  return new Date(ts).toLocaleDateString(undefined, { weekday: "short" });
}

type CardShellProps = {
  eyebrow: string;
  title: string;
  hint: string;
  to: string;
  children: React.ReactNode;
};

function CardShell({ eyebrow, title, hint, to, children }: CardShellProps) {
  return (
    <Card className="min-h-[220px] ring-border">
      <CardHeader>
        <div className="flex items-baseline justify-between gap-3">
          <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
            {eyebrow}
          </div>
          <Link
            to={to}
            className="text-[12px] font-medium text-[var(--wt-text-secondary)] hover:text-foreground"
          >
            View
          </Link>
        </div>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{hint}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-end gap-2 py-4">
        {children}
      </CardContent>
    </Card>
  );
}

function EmptyCardBody({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 text-[var(--wt-text-muted)]">
      <Icon className="size-[22px]" />
      <div className="text-sm font-medium text-muted-foreground">No data</div>
      <div className="text-xs text-[var(--wt-text-muted)]">
        Nothing on the record yet
      </div>
    </div>
  );
}

function RunsCard({ simulations }: { simulations: Simulation[] }) {
  const week = useMemo(() => {
    const today = startOfDay(Date.now());
    const days = Array.from({ length: 7 }, (_, i) => today - (6 - i) * DAY_MS);
    const counts = new Map<number, number>(days.map((d) => [d, 0]));
    for (const s of simulations) {
      const ts = Date.parse(s.created_at);
      if (Number.isNaN(ts)) continue;
      const day = startOfDay(ts);
      if (counts.has(day)) counts.set(day, (counts.get(day) || 0) + 1);
    }
    const series = days.map((d) => ({ day: d, count: counts.get(d) || 0 }));
    const total = series.reduce((acc, p) => acc + p.count, 0);
    return { series, total };
  }, [simulations]);

  if (simulations.length === 0) return <EmptyCardBody icon={Activity} />;

  const max = Math.max(1, ...week.series.map((p) => p.count));
  return (
    <>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold text-foreground">{week.total}</span>
        <span className="text-[13px] text-[var(--wt-text-secondary)]">
          call{week.total === 1 ? "" : "s"} in the last 7 days
        </span>
      </div>
      <div className="flex h-16 items-end gap-1.5">
        {week.series.map((p) => (
          <div key={p.day} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="w-full rounded-sm bg-[var(--wt-green-500)]"
              style={{
                height: `${Math.max(p.count > 0 ? 8 : 2, (p.count / max) * 100)}%`,
                opacity: p.count > 0 ? 1 : 0.25,
              }}
              title={`${p.count} on ${new Date(p.day).toLocaleDateString()}`}
            />
            <span className="text-[10px] text-[var(--wt-text-muted)]">
              {dayLabel(p.day)}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

function VerdictCard({ evaluations }: { evaluations: EvaluationRun[] }) {
  const latest = evaluations.find((r) => r.total > 0);
  if (!latest) return <EmptyCardBody icon={LineChart} />;

  const inconclusive = latest.inconclusive || 0;
  const segments = [
    { label: "Clean", count: latest.passed, className: "bg-pass" },
    { label: "Flagged", count: latest.failed, className: "bg-[var(--wt-danger)]" },
    { label: "Inconclusive", count: inconclusive, className: "bg-warn" },
  ].filter((s) => s.count > 0);

  return (
    <>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold text-foreground">
          {latest.total > 0 ? Math.round((latest.passed / latest.total) * 100) : 0}%
        </span>
        <span className="text-[13px] text-[var(--wt-text-secondary)]">
          clean in {latest.suite_id}
        </span>
      </div>
      <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full bg-[var(--wt-section)]">
        {segments.map((s) => (
          <div
            key={s.label}
            className={cn("h-full", s.className)}
            style={{ width: `${(s.count / latest.total) * 100}%` }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5 text-[12px]">
            <span className={cn("size-2 rounded-full", s.className)} />
            <span className="text-[var(--wt-text-secondary)]">
              {s.count} {s.label.toLowerCase()}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

function AgentsCard({ agents }: { agents: AgentRow[] }) {
  if (agents.length === 0) return <EmptyCardBody icon={Bot} />;

  const shown = agents.slice(0, 3);
  return (
    <>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold text-foreground">{agents.length}</span>
        <span className="text-[13px] text-[var(--wt-text-secondary)]">
          agent{agents.length === 1 ? "" : "s"} on the record
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {shown.map((a, i) => {
          const ready = Boolean(a.connected || a.agent_id);
          return (
            <div
              key={a.id || a.agent_id || a.suite || i}
              className="flex items-center gap-2 text-[13px]"
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  ready ? "bg-pass" : "bg-warn",
                )}
              />
              <span className="truncate text-foreground">
                {a.name || a.agent_id || a.id || a.suite || "Untitled agent"}
              </span>
              <span className="ml-auto shrink-0 text-[12px] text-[var(--wt-text-muted)]">
                {a.platform || a.transport || "—"}
              </span>
            </div>
          );
        })}
        {agents.length > shown.length && (
          <div className="text-[12px] text-[var(--wt-text-muted)]">
            +{agents.length - shown.length} more
          </div>
        )}
      </div>
    </>
  );
}

function SuitesCard({ suites }: { suites: SuiteSummary[] }) {
  if (suites.length === 0) return <EmptyCardBody icon={Layers} />;

  const scenarios = suites.reduce((acc, s) => acc + (s.scenario_count || 0), 0);
  const shown = suites.slice(0, 3);
  return (
    <>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold text-foreground">{suites.length}</span>
        <span className="text-[13px] text-[var(--wt-text-secondary)]">
          suite{suites.length === 1 ? "" : "s"} · {scenarios} scenario
          {scenarios === 1 ? "" : "s"}
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {shown.map((s) => (
          <div key={s.path} className="flex items-center gap-2 text-[13px]">
            <span className="truncate text-foreground">{s.name}</span>
            <span className="ml-auto shrink-0 text-[12px] text-[var(--wt-text-muted)]">
              {s.scenario_count ?? 0} scenario{(s.scenario_count ?? 0) === 1 ? "" : "s"}
            </span>
          </div>
        ))}
        {suites.length > shown.length && (
          <div className="text-[12px] text-[var(--wt-text-muted)]">
            +{suites.length - shown.length} more
          </div>
        )}
      </div>
    </>
  );
}

export function DashboardPage() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([
      client.simulations(200),
      client.evaluations(40),
      client.agents(),
      client.suites(),
    ]).then(([sims, evals, ags, sts]) => {
      if (!alive) return;
      if (sims.status === "fulfilled") setSimulations(sims.value);
      if (evals.status === "fulfilled") setEvaluations(evals.value);
      if (ags.status === "fulfilled") setAgents(ags.value);
      if (sts.status === "fulfilled") setSuites(sts.value);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-5">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-baseline gap-2.5">
            <h1 className="text-[22px] font-semibold tracking-[-0.005em] text-foreground">
              Dashboard
            </h1>
            <span className="text-[13px] font-medium text-[var(--wt-text-muted)]">
              1 dashboard
            </span>
          </div>
          <p className="max-w-xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
            What the taps see, at a glance.
          </p>
        </div>
        <Button asChild>
          <Link to="/suites">Open suites</Link>
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <CardShell
          eyebrow="Runs"
          title="Runs this week"
          hint="How many calls you put on the record."
          to="/evaluations"
        >
          {loading ? null : <RunsCard simulations={simulations} />}
        </CardShell>
        <CardShell
          eyebrow="Verdict"
          title="Clean vs flagged"
          hint="The split across your latest suite."
          to="/evaluations"
        >
          {loading ? null : <VerdictCard evaluations={evaluations} />}
        </CardShell>
        <CardShell
          eyebrow="Agents"
          title="Agents under tap"
          hint="The voice agents you're watching."
          to="/agents"
        >
          {loading ? null : <AgentsCard agents={agents} />}
        </CardShell>
        <CardShell
          eyebrow="Suites"
          title="Suites on record"
          hint="The test suites ready to dial."
          to="/suites"
        >
          {loading ? null : <SuitesCard suites={suites} />}
        </CardShell>
      </div>
    </div>
  );
}
