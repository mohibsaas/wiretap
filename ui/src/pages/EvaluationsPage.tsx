import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  CircleDot,
  MoreHorizontal,
  Play,
  Plus,
  Search,
  Square,
  X,
} from "lucide-react";
import { NewRunDialog } from "@/components/NewRunDialog";
import { PageHeader } from "@/components/PageHeader";
import { TruncatedText } from "@/components/TruncatedText";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
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
  type EvaluationRun,
  type Simulation,
  type SuiteSummary,
} from "@/lib/api";
import { formatRelative, passRatePercent, runDuration, runVerdict, simulationVerdict } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "runs" | "simulations";

const segmentTabClass = cn(
  "box-border h-[30px] flex-none rounded-[9px] border border-transparent px-[18px] py-0 text-[13.5px] font-medium text-foreground shadow-none",
  "hover:text-foreground data-active:border-border data-active:bg-card data-active:font-semibold data-active:text-foreground",
  "data-active:shadow-[0_1px_2px_rgba(41,41,39,0.06)] dark:data-active:border-border dark:data-active:bg-card",
);

export function EvaluationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const runFromUrl = searchParams.get("run");
  const [tab, setTab] = useState<Tab>(runFromUrl ? "simulations" : "runs");
  const [evals, setEvals] = useState<EvaluationRun[]>([]);
  const [sims, setSims] = useState<Simulation[]>([]);
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  /** Selected run instance (batch_id) — filters the Simulations tab. */
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(
    runFromUrl,
  );
  const [error, setError] = useState<string | null>(null);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [seedSuite, setSeedSuite] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      void client
        .evaluations(80)
        .then(setEvals)
        .catch((e: Error) => setError(e.message));
      void client
        .simulations(120)
        .then(setSims)
        .catch(() => setSims([]));
      void client
        .suites()
        .then((rows) => setSuites(rows.filter((s) => !s.error)))
        .catch(() => setSuites([]));
    };
    load();
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  useEffect(() => {
    if (!runFromUrl) return;
    setSelectedBatchId(runFromUrl);
    setTab("simulations");
  }, [runFromUrl]);

  const platforms = useMemo(() => {
    const set = new Set<string>();
    for (const s of suites) if (s.platform) set.add(s.platform);
    return [...set].sort();
  }, [suites]);

  const selectedRun = useMemo(
    () => evals.find((r) => r.batch_id === selectedBatchId) || null,
    [evals, selectedBatchId],
  );

  const runRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return evals.filter((r) => {
      if (agentFilter !== "all") {
        const suite = suites.find((s) => s.name === r.suite_id);
        if (suite?.platform !== agentFilter) return false;
      }
      if (statusFilter !== "all") {
        const st = (r.status || "").toLowerCase();
        if (statusFilter === "passed") {
          if ((r.failed || 0) > 0 || (r.total || 0) === 0) return false;
        } else if (statusFilter === "failed") {
          if ((r.failed || 0) === 0) return false;
        } else if (st !== statusFilter) return false;
      }
      if (!q) return true;
      return (
        (r.suite_id || "").toLowerCase().includes(q) ||
        r.batch_id.toLowerCase().includes(q)
      );
    });
  }, [evals, suites, query, statusFilter, agentFilter]);

  const simulationRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sims.filter((s) => {
      if (selectedBatchId && s.batch_id !== selectedBatchId) return false;
      if (agentFilter !== "all") {
        const suite = suites.find((su) => su.name === s.suite_id);
        const platform =
          suite?.platform ||
          (typeof s.meta?.platform === "string" ? s.meta.platform : null);
        if (platform !== agentFilter) return false;
      }
      if (statusFilter !== "all") {
        if (statusFilter === "passed" && !s.passed) return false;
        if (statusFilter === "failed" && (s.passed || s.meta?.inconclusive))
          return false;
        if (statusFilter === "completed") {
          /* simulations are finished artifacts */
        } else if (
          statusFilter !== "passed" &&
          statusFilter !== "failed" &&
          statusFilter !== "running"
        ) {
          /* ignore run-level statuses on sim list */
        }
      }
      if (!q) return true;
      return (
        (s.scenario_name || "").toLowerCase().includes(q) ||
        (s.scenario_id || "").toLowerCase().includes(q) ||
        (s.persona_name || "").toLowerCase().includes(q) ||
        (s.suite_id || "").toLowerCase().includes(q) ||
        (s.batch_id || "").toLowerCase().includes(q) ||
        s.simulation_id.toLowerCase().includes(q)
      );
    });
  }, [sims, suites, query, statusFilter, agentFilter, selectedBatchId]);

  const sectionCount = tab === "runs" ? runRows.length : simulationRows.length;

  function openNewRun(suite?: string) {
    setSeedSuite(suite || null);
    setNewRunOpen(true);
  }

  function selectRun(batchId: string) {
    setSelectedBatchId(batchId);
    setTab("simulations");
    setSearchParams({ run: batchId }, { replace: true });
  }

  function clearSelectedRun() {
    setSelectedBatchId(null);
    setSearchParams({}, { replace: true });
  }

  function onTabChange(next: Tab) {
    setTab(next);
    if (next === "runs") {
      setSelectedBatchId(null);
      setSearchParams({}, { replace: true });
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Simulations"
        subtitle="Pressure-test your agents before your customers do."
        meta={`${evals.length} run${evals.length === 1 ? "" : "s"}`}
        action={
          <Button onClick={() => openNewRun()}>
            <Plus data-icon="inline-start" />
            New run
          </Button>
        }
      />

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-baseline gap-2.5">
              <h2 className="text-[17px] font-semibold tracking-[-0.01em] text-foreground">
                {tab === "runs" ? "Runs" : "Simulations"}
              </h2>
              <span className="font-mono text-[12.5px] text-[var(--wt-text-muted)] tabular-nums">
                {sectionCount}
              </span>
            </div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground text-pretty">
              {tab === "runs"
                ? "Each run is one suite execution. Open a run to review every test it produced."
                : selectedRun
                  ? "Tests from the selected run."
                  : "Individual test results across runs."}
            </p>
          </div>
          <div className="relative w-full max-w-[280px]">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search runs, agents, simulations…"
              className="h-9 rounded-[10px] pl-9"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Tabs
            value={tab}
            onValueChange={(v) => onTabChange(v as Tab)}
            className="gap-0"
          >
            <TabsList className="box-border flex h-9 items-center gap-0.5 rounded-xl bg-[var(--wt-section)] p-[3px] text-foreground">
              <TabsTrigger value="runs" className={segmentTabClass}>
                Runs
              </TabsTrigger>
              <TabsTrigger value="simulations" className={segmentTabClass}>
                All simulations
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {selectedRun && (
            <button
              type="button"
              onClick={clearSelectedRun}
              className="inline-flex h-9 max-w-[320px] items-center gap-1.5 rounded-full border border-primary bg-accent px-3 text-[12.5px] font-medium text-primary transition-colors hover:bg-[var(--wt-green-100)]"
              aria-label="Clear run filter"
            >
              <span className="truncate">
                <span className="opacity-80">Run:</span>{" "}
                {selectedRun.suite_id || selectedRun.batch_id.slice(0, 8)}
              </span>
              <X className="size-3.5 shrink-0 opacity-80" />
            </button>
          )}

          <div className="h-5 w-px bg-border" />

          <FilterDropdown
            icon={<Square className="size-3.5" />}
            label="Agent"
            value={agentFilter}
            onChange={setAgentFilter}
            options={[
              { value: "all", label: "All platforms" },
              ...platforms.map((p) => ({ value: p, label: p })),
            ]}
          />
          <FilterDropdown
            icon={<CircleDot className="size-3.5" />}
            label="Status"
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: "all", label: "All statuses" },
              { value: "completed", label: "Completed" },
              { value: "running", label: "Running" },
              { value: "failed", label: "Failed" },
              { value: "passed", label: "Passed" },
            ]}
          />
        </div>

        {error && <p className="text-sm text-fail">{error}</p>}

        {tab === "runs" ? (
          <div className="flex flex-col gap-2.5">
            {runRows.length === 0 && (
              <EmptyRow
                title="No runs yet"
                body="Import or generate a suite, then hit New run."
              />
            )}
            {runRows.map((r) => {
              const verdict = runVerdict(r.passed, r.failed, r.total);
              const suite = suites.find((s) => s.name === r.suite_id);
              const rate = passRatePercent(r.passed, r.total);
              return (
                <div
                  key={r.batch_id}
                  className="group flex items-center gap-3.5 rounded-xl border border-border bg-card px-[18px] py-3.5 transition-colors hover:border-[var(--wt-border-strong)] hover:bg-[var(--wt-section)]"
                >
                  <button
                    type="button"
                    onClick={() => selectRun(r.batch_id)}
                    className="flex min-w-0 flex-1 items-center gap-3.5 text-left"
                  >
                    <div className="flex size-[34px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-primary">
                      <Play className="size-4 fill-current" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <TruncatedText
                        text={r.suite_id || "suite"}
                        className="text-[14.5px] font-semibold"
                      />
                      <div className="truncate text-[12.5px] text-muted-foreground">
                        {[
                          suite?.platform,
                          `${r.total} test${r.total === 1 ? "" : "s"}`,
                          `${r.passed} passed`,
                          rate,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </div>
                    <div className="hidden items-center gap-4 sm:flex">
                      <div className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
                        <span
                          className={cn(
                            "size-1.5 rounded-full",
                            verdict.variant === "pass" && "bg-pass",
                            verdict.variant === "fail" && "bg-fail",
                            verdict.variant === "warn" && "bg-warn",
                            verdict.variant === "muted" && "bg-muted-foreground",
                          )}
                        />
                        {verdict.label}
                      </div>
                      <div className="font-mono text-xs text-[var(--wt-text-muted)] tabular-nums">
                        {formatRelative(r.created_at)} ·{" "}
                        {runDuration(r.created_at, r.finished_at)}
                      </div>
                    </div>
                  </button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" aria-label="More">
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuGroup>
                        <DropdownMenuItem onClick={() => selectRun(r.batch_id)}>
                          View tests
                        </DropdownMenuItem>
                        {r.suite_id && (
                          <DropdownMenuItem onClick={() => openNewRun(r.suite_id)}>
                            New run
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuGroup>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {simulationRows.length === 0 && (
              <EmptyRow
                title="No simulations yet"
                body={
                  selectedBatchId
                    ? "This run has no saved test results."
                    : "Launch a New run against a suite to put results on the record."
                }
              />
            )}
            {simulationRows.map((s) => (
              <Link
                key={s.simulation_id}
                to={
                  s.batch_id
                    ? `/evaluations/${s.batch_id}/scenarios/${s.simulation_id}`
                    : `/evaluations`
                }
                className="flex items-center gap-3.5 rounded-xl border border-border bg-card px-[18px] py-3.5 transition-colors hover:border-[var(--wt-border-strong)] hover:bg-[var(--wt-section)]"
              >
                <div className="flex size-[34px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-primary">
                  <Play className="size-4 fill-current" />
                </div>
                <div className="min-w-0 flex-1">
                  <TruncatedText
                    text={s.scenario_name || s.scenario_id || "Scenario"}
                    className="text-[14.5px] font-semibold"
                  />
                  <div className="truncate text-[12.5px] text-muted-foreground">
                    {[
                      s.persona_name || s.persona_id,
                      s.suite_id,
                      s.created_at ? formatRelative(s.created_at) : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
                {(() => {
                  const v = simulationVerdict(s);
                  return (
                    <Badge variant={v.variant}>
                      {v.pct != null
                        ? `${v.label.toLowerCase()} · ${v.pct}%`
                        : v.label.toLowerCase()}
                    </Badge>
                  );
                })()}
                <span className="hidden font-mono text-xs text-[var(--wt-text-muted)] tabular-nums sm:inline">
                  {s.transcript?.length || 0} turns
                </span>
                <ChevronRight className="size-3.5 text-muted-foreground" />
              </Link>
            ))}
          </div>
        )}
      </section>

      <NewRunDialog
        open={newRunOpen}
        onOpenChange={setNewRunOpen}
        initialSuite={seedSuite}
      />
    </div>
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
            <DropdownMenuRadioItem
              key={o.value}
              value={o.value}
              className="rounded-md py-1.5 pr-8 pl-2"
            >
              {o.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function EmptyRow({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--wt-border-strong)] bg-[var(--wt-section)] px-8 py-16 text-center">
      <div className="text-base font-semibold">{title}</div>
      <div className="mx-auto mt-1.5 max-w-sm text-[13px] text-muted-foreground text-pretty">
        {body}
      </div>
    </div>
  );
}
