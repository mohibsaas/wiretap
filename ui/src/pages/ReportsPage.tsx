import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Search, SlidersHorizontal, Square } from "lucide-react";
import {
  CategorySpark,
  ReportBadgeChip,
  ReportScorePlate,
  ReportStatusPill,
} from "@/components/ReportChrome";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  client,
  type AgentRow,
  type EvaluationRun,
  type Simulation,
  type SuiteDetail,
  type SuiteSummary,
} from "@/lib/api";
import { formatRelative } from "@/lib/format";
import {
  REPORT_CATEGORIES,
  buildReport,
  indexSuiteScenarios,
  reportMetaLine,
  resolveAgentName,
  simsForRun,
  type ReportStatus,
  type ReportView,
} from "@/lib/reports";
import { cn } from "@/lib/utils";

const segmentTabClass = cn(
  "box-border h-[30px] flex-none rounded-[9px] border border-transparent px-[18px] py-0 text-[13.5px] font-medium text-foreground shadow-none",
  "hover:text-foreground data-active:border-border data-active:bg-card data-active:font-semibold data-active:text-foreground",
  "data-active:shadow-[0_1px_2px_rgba(41,41,39,0.06)] dark:data-active:border-border dark:data-active:bg-card",
);

type StatusFilter = "all" | ReportStatus;
type CoverageFilter = "all" | "full" | "partial";

export function ReportsPage() {
  const [evals, setEvals] = useState<EvaluationRun[]>([]);
  const [sims, setSims] = useState<Simulation[]>([]);
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [suiteDetails, setSuiteDetails] = useState<
    Record<string, SuiteDetail | null>
  >({});
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [agentFilter, setAgentFilter] = useState("all");
  const [coverageFilter, setCoverageFilter] = useState<CoverageFilter>("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([
      client.evaluations(80),
      client.simulations(200),
      client.suites(),
      client.agents(),
    ]).then(([ev, sm, st, ag]) => {
      if (!alive) return;
      if (ev.status === "fulfilled") setEvals(ev.value);
      else setError(ev.reason instanceof Error ? ev.reason.message : "Failed to load reports");
      if (sm.status === "fulfilled") setSims(sm.value);
      if (st.status === "fulfilled") setSuites(st.value.filter((s) => !s.error));
      if (ag.status === "fulfilled") setAgents(ag.value);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const names = [...new Set(evals.map((r) => r.suite_id).filter(Boolean))];
    const missing = names.filter((n) => !(n in suiteDetails));
    if (missing.length === 0) return;
    let alive = true;
    void Promise.all(
      missing.map((name) =>
        client
          .suite(name)
          .then((d) => [name, d] as const)
          .catch(() => [name, null] as const),
      ),
    ).then((rows) => {
      if (!alive) return;
      setSuiteDetails((prev) => {
        const next = { ...prev };
        for (const [name, detail] of rows) next[name] = detail;
        return next;
      });
    });
    return () => {
      alive = false;
    };
  }, [evals, suiteDetails]);

  const reports = useMemo(() => {
    return evals.map((run) => {
      const members = simsForRun(run, sims);
      const suite = suiteDetails[run.suite_id] || null;
      const summary = suites.find((s) => s.name === run.suite_id) || null;
      return buildReport({
        run,
        sims: members,
        index: indexSuiteScenarios(suite),
        agent: resolveAgentName(run, agents, suite || summary, members),
      });
    });
  }, [evals, sims, suiteDetails, suites, agents]);

  const agentOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of reports) if (r.agent) set.add(r.agent);
    return [...set].sort();
  }, [reports]);

  const counts = useMemo(() => {
    const clean = reports.filter((r) => r.status === "Clean").length;
    const flagged = reports.filter((r) => r.status === "Flagged").length;
    return { all: reports.length, Clean: clean, Flagged: flagged };
  }, [reports]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return reports.filter((r) => {
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      if (agentFilter !== "all" && r.agent !== agentFilter) return false;
      if (coverageFilter === "full" && !r.full) return false;
      if (coverageFilter === "partial" && r.full) return false;
      if (!q) return true;
      return (
        r.name.toLowerCase().includes(q) ||
        r.agent.toLowerCase().includes(q) ||
        r.suiteId.toLowerCase().includes(q) ||
        r.hash.includes(q) ||
        r.batchId.toLowerCase().includes(q)
      );
    });
  }, [reports, query, statusFilter, agentFilter, coverageFilter]);

  return (
    <div className="flex flex-col gap-6 pb-16">
      <PageHeader
        title="Reports"
        meta={`${reports.length} report${reports.length === 1 ? "" : "s"}`}
        subtitle="Scores, badges, and per-category breakdowns for each run — open one for the fixes it suggests."
      />

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Tabs
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as StatusFilter)}
            className="gap-0"
          >
            <TabsList className="box-border flex h-9 items-center gap-0.5 rounded-xl bg-[var(--wt-section)] p-[3px] text-foreground">
              <TabsTrigger value="all" className={segmentTabClass}>
                All {counts.all}
              </TabsTrigger>
              <TabsTrigger value="Clean" className={segmentTabClass}>
                Clean {counts.Clean}
              </TabsTrigger>
              <TabsTrigger value="Flagged" className={segmentTabClass}>
                Flagged {counts.Flagged}
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="h-5 w-px bg-border" />

          <FilterDropdown
            icon={<Square className="size-3.5" />}
            label="Agent"
            value={agentFilter}
            onChange={setAgentFilter}
            options={[
              { value: "all", label: "All agents" },
              ...agentOptions.map((a) => ({ value: a, label: a })),
            ]}
          />
          <FilterDropdown
            icon={<SlidersHorizontal className="size-3.5" />}
            label="Coverage"
            value={coverageFilter}
            onChange={(v) => setCoverageFilter(v as CoverageFilter)}
            options={[
              { value: "all", label: "Any coverage" },
              { value: "full", label: `All ${REPORT_CATEGORIES.length} categories` },
              { value: "partial", label: "Partial" },
            ]}
          />

          <div className="relative ml-auto w-full max-w-[280px] shrink-0">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search reports, agents, suites…"
              className="h-9 rounded-[10px] pl-9"
            />
          </div>
        </div>

        {error && <p className="text-sm text-fail">{error}</p>}

        <div className="flex flex-col gap-2.5">
          {shown.length === 0 && (
            <div className="rounded-2xl border border-dashed border-[var(--wt-border-strong)] bg-[var(--wt-section)] px-8 py-16 text-center">
              <div className="text-base font-semibold">
                {reports.length === 0 ? "No reports yet" : "No matching reports"}
              </div>
              <div className="mx-auto mt-1.5 max-w-sm text-[13px] text-muted-foreground text-pretty">
                {reports.length === 0
                  ? "Run a suite from Simulations. Each finished run leaves a report here."
                  : "Clear filters or try a different search."}
              </div>
            </div>
          )}
          {shown.map((r) => (
            <ReportCard key={r.batchId} report={r} />
          ))}
        </div>
      </section>
    </div>
  );
}

function ReportCard({ report }: { report: ReportView }) {
  const clean = report.status === "Clean";
  const earned = report.badges.filter((b) => b.met).length;
  const checkLine = report.flaggedCount
    ? `${report.flaggedCount} of ${report.simCount} checks flagged`
    : report.simCount
      ? `all ${report.simCount} checks passed`
      : "no simulations yet";
  return (
    <Link
      to={`/reports/${encodeURIComponent(report.batchId)}`}
      className="flex items-center gap-4 rounded-[14px] border border-border bg-card px-[18px] py-[15px] transition-colors hover:border-[var(--wt-border-strong)] hover:bg-[var(--wt-section)]"
    >
      <ReportScorePlate score={report.overall} clean={clean} />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-[14.5px] font-semibold leading-snug text-foreground">
            {report.name}
          </span>
          <ReportStatusPill status={report.status} />
        </div>
        <div className="text-[12.5px] leading-snug text-muted-foreground">
          {reportMetaLine(report)}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2.5">
          <CategorySpark scores={report.scores} />
          <span className="text-[11.5px] text-muted-foreground">
            {report.covered.length} of {REPORT_CATEGORIES.length} categories
          </span>
          <span className="inline-block size-[3px] rounded-full bg-[var(--wt-text-muted)]" />
          <span className="text-[11.5px] text-muted-foreground">{checkLine}</span>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <ReportBadgeChip full={report.full} earned={earned} />
        <span className="font-mono text-[11.5px] text-[var(--wt-text-muted)]">
          {formatRelative(report.createdAt)}
        </span>
      </div>
      <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
    </Link>
  );
}

function FilterDropdown({
  icon,
  label,
  value,
  onChange,
  options,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  const selected = options.find((o) => o.value === value)?.label;
  const active = value !== "all";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(
            "h-9 gap-1.5 rounded-[10px]",
            active && "border-primary bg-accent text-accent-foreground",
          )}
        >
          {icon}
          <span>{label}</span>
          {active && (
            <span className="max-w-[90px] truncate text-muted-foreground">
              {selected}
            </span>
          )}
          <ChevronDown data-icon="inline-end" className="opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-48 p-1.5">
        <DropdownMenuLabel className="px-2 py-1.5">{label}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
          {options.map((o) => (
            <DropdownMenuRadioItem key={o.value} value={o.value}>
              {o.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
