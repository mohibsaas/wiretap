import {
  ChevronRight,
  CircleDot,
  Loader2,
  MoreHorizontal,
  Play,
  Plus,
  Search,
  Square,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { NewRunDialog } from "@/components/NewRunDialog";
import { FilterMenu } from "@/components/FilterMenu";
import { PageHeader } from "@/components/PageHeader";
import { ScenarioProgressRow } from "@/components/ScenarioProgressRow";
import { TruncatedText } from "@/components/TruncatedText";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  client,
  type EvaluationRun,
  type RunProgress,
  type Simulation,
  type SuiteSummary,
} from "@/lib/api";
import {
  formatRelative,
  passRatePercent,
  runDuration,
  runVerdict,
  simulationVerdict,
} from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "runs" | "simulations";

const segmentTabClass = cn(
  "box-border h-[30px] flex-none rounded-[9px] border border-transparent px-[18px] py-0 text-[13.5px] font-medium text-foreground shadow-none",
  "hover:text-foreground data-active:border-border data-active:bg-card data-active:font-semibold data-active:text-foreground",
  "data-active:shadow-[0_1px_2px_rgba(41,41,39,0.06)] dark:data-active:border-border dark:data-active:bg-card",
);

export function EvaluationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
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
  const [activeProgress, setActiveProgress] = useState<RunProgress[]>(() => {
    const seed = (location.state as { seedProgress?: RunProgress } | null)
      ?.seedProgress;
    return seed?.batch_id ? [seed] : [];
  });

  // Keep optimistic rows from New run / re-run navigation.
  useEffect(() => {
    const seed = (location.state as { seedProgress?: RunProgress } | null)
      ?.seedProgress;
    if (!seed?.batch_id) return;
    setActiveProgress((prev) => {
      if (prev.some((p) => p.batch_id === seed.batch_id)) return prev;
      return [seed, ...prev];
    });
    setSelectedBatchId(seed.batch_id);
    setTab("simulations");
  }, [location.state]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [ev, si, su, active] = await Promise.all([
          client.evaluations(80),
          client.simulations(120).catch(() => [] as Simulation[]),
          client.suites().catch(() => [] as SuiteSummary[]),
          client.activeEvaluationProgress().catch(() => [] as RunProgress[]),
        ]);
        if (cancelled) return;
        setEvals(ev);
        setSims(si);
        setSuites(su.filter((s) => !s.error));

        let nextProgress = active;
        if (selectedBatchId) {
          try {
            const one = await client.evaluationProgress(selectedBatchId);
            nextProgress = [
              one,
              ...active.filter((p) => p.batch_id !== one.batch_id),
            ];
          } catch {
            /* finished or not on disk yet — keep optimistic seed below */
          }
        }
        if (cancelled) return;
        setActiveProgress((prev) => {
          const byId = new Map(nextProgress.map((p) => [p.batch_id, p]));
          // Keep seeded rows for the open run until the server has them (or the run ends).
          for (const p of prev) {
            if (byId.has(p.batch_id)) continue;
            if (p.batch_id !== selectedBatchId) continue;
            const run = ev.find((e) => e.batch_id === p.batch_id);
            const st = (run?.status || "").toLowerCase();
            if (run && st !== "running" && st !== "pending") continue;
            if ((p.scenarios?.length || 0) === 0) continue;
            byId.set(p.batch_id, p);
          }
          return [...byId.values()];
        });
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void load();
    const poll = window.setInterval(() => void load(), 1500);
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
      window.removeEventListener("focus", onFocus);
    };
  }, [selectedBatchId]);

  useEffect(() => {
    if (!runFromUrl) return;
    setSelectedBatchId(runFromUrl);
    setTab("simulations");
  }, [runFromUrl]);

  const progressByBatch = useMemo(() => {
    const map = new Map<string, RunProgress>();
    for (const p of activeProgress) map.set(p.batch_id, p);
    return map;
  }, [activeProgress]);

  const selectedProgress = selectedBatchId
    ? progressByBatch.get(selectedBatchId) || null
    : null;

  /** Include live CLI/UI runs even if the stub summary is briefly missing. */
  const evalsMerged = useMemo(() => {
    const byId = new Map(evals.map((e) => [e.batch_id, e]));
    for (const p of activeProgress) {
      const existing = byId.get(p.batch_id);
      const scenarioIds =
        p.scenarios?.map((s) => s.scenario_id).filter(Boolean) || [];
      if (existing) {
        byId.set(p.batch_id, {
          ...existing,
          status: existing.status || p.status || "running",
          suite_id: existing.suite_id || p.suite_id || "",
          scenario_ids:
            existing.scenario_ids?.length ? existing.scenario_ids : scenarioIds,
          total:
            existing.total ||
            p.total ||
            scenarioIds.length ||
            existing.scenario_ids?.length ||
            0,
        });
        continue;
      }
      byId.set(p.batch_id, {
        batch_id: p.batch_id,
        suite_id: p.suite_id || "",
        status: "running",
        created_at: p.created_at,
        finished_at: null,
        scenario_ids: scenarioIds,
        passed: 0,
        failed: 0,
        total: p.total || scenarioIds.length || 0,
      });
    }
    return [...byId.values()].sort((a, b) =>
      String(b.created_at || "").localeCompare(String(a.created_at || "")),
    );
  }, [evals, activeProgress]);

  const platforms = useMemo(() => {
    const set = new Set<string>();
    for (const s of suites) if (s.platform) set.add(s.platform);
    return [...set].sort();
  }, [suites]);

  const selectedRun = useMemo(
    () => evalsMerged.find((r) => r.batch_id === selectedBatchId) || null,
    [evalsMerged, selectedBatchId],
  );

  const runRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return evalsMerged.filter((r) => {
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
  }, [evalsMerged, suites, query, statusFilter, agentFilter]);

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

  /** In-progress (or just-started) cases — not only finished pass/fail artifacts. */
  const liveScenarioRows = useMemo(() => {
    if (!selectedBatchId || tab !== "simulations") return null;
    if (statusFilter === "passed" || statusFilter === "failed") return null;

    const fromProgress = selectedProgress?.scenarios;
    if (fromProgress && fromProgress.length > 0) return fromProgress;

    const st = (selectedRun?.status || "").toLowerCase();
    const isLive =
      st === "running" ||
      st === "pending" ||
      progressByBatch.has(selectedBatchId);
    const ids = selectedRun?.scenario_ids || [];
    if (!isLive || ids.length === 0) return null;

    // Stub rows from the evaluation summary until progress/SSE catches up.
    return ids.map((id) => ({
      scenario_id: id,
      scenario_name: id,
      phase: "queued",
      detail: "starting…",
      turn: 0,
      simulation_id: null,
      passed: null,
      inconclusive: null,
      error: null,
    }));
  }, [
    selectedBatchId,
    tab,
    statusFilter,
    selectedProgress,
    selectedRun,
    progressByBatch,
  ]);

  // Once the run finishes, prefer finished sim artifacts over stale seed rows.
  const showLiveCases =
    (liveScenarioRows?.length || 0) > 0 &&
    ((selectedRun?.status || "").toLowerCase() === "running" ||
      (selectedRun?.status || "").toLowerCase() === "pending" ||
      !!selectedProgress ||
      simulationRows.length === 0);

  const sectionCount =
    tab === "runs"
      ? runRows.length
      : showLiveCases
        ? liveScenarioRows!.length
        : simulationRows.length;

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
        meta={`${evalsMerged.length} run${evalsMerged.length === 1 ? "" : "s"}`}
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

          <FilterMenu
            icon={<Square className="size-3.5" />}
            label="Agent"
            value={agentFilter}
            onChange={setAgentFilter}
            options={[
              { value: "all", label: "All platforms" },
              ...platforms.map((p) => ({ value: p, label: p })),
            ]}
          />
          <FilterMenu
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
              const isRunning =
                (r.status || "").toLowerCase() === "running" ||
                progressByBatch.has(r.batch_id);
              const verdict = isRunning
                ? { label: "Running", variant: "warn" as const }
                : runVerdict(r.passed, r.failed, r.total);
              const suite = suites.find((s) => s.name === r.suite_id);
              const rate = isRunning
                ? `${progressByBatch.get(r.batch_id)?.done ?? 0}/${r.total}`
                : passRatePercent(r.passed, r.total);
              const live = progressByBatch.get(r.batch_id);
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
                          isRunning
                            ? live
                              ? `${live.done ?? 0} done`
                              : "in progress"
                            : `${r.passed} passed`,
                          rate,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </div>
                    <div className="hidden items-center gap-4 sm:flex">
                      <div className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
                        {isRunning ? (
                          <Loader2
                            className="size-3.5 animate-spin text-primary/70"
                            aria-hidden
                          />
                        ) : (
                          <span
                            className={cn(
                              "size-1.5 rounded-full",
                              verdict.variant === "pass" && "bg-pass",
                              verdict.variant === "fail" && "bg-fail",
                              verdict.variant === "warn" && "bg-warn",
                              verdict.variant === "muted" &&
                                "bg-muted-foreground",
                            )}
                          />
                        )}
                        {verdict.label}
                      </div>
                      <div className="font-mono text-xs text-[var(--wt-text-muted)] tabular-nums">
                        {formatRelative(r.created_at)}
                        {!isRunning &&
                          ` · ${runDuration(r.created_at, r.finished_at)}`}
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
            {showLiveCases ? (
              liveScenarioRows!.map((row) => (
                <ScenarioProgressRow
                  key={row.scenario_id}
                  row={row}
                  batchId={selectedBatchId!}
                />
              ))
            ) : (
              <>
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
              </>
            )}
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
