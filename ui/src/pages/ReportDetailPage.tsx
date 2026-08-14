import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Check,
  ChevronLeft,
  Download,
  Lock,
  RefreshCw,
  Share2,
  X,
} from "lucide-react";
import {
  ApplyPromptDialog,
  promptFindingIdsForScenario,
  usePromptApply,
} from "@/components/ApplyPromptDialog";
import { NewRunDialog } from "@/components/NewRunDialog";
import {
  ReportBadgePlate,
  ReportStatusPill,
} from "@/components/ReportChrome";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  client,
  type AgentRow,
  type EvaluationRun,
  type SuiteDetail,
} from "@/lib/api";
import { formatRelative } from "@/lib/format";
import {
  REPORT_CATEGORIES,
  badgePackSvg,
  buildReport,
  categoryLabel,
  downloadText,
  indexSuiteScenarios,
  resolveAgentName,
  scoreBand,
  type ReportBadge,
  type ReportView,
} from "@/lib/reports";
import { cn } from "@/lib/utils";

const segmentTabClass = cn(
  "box-border h-[30px] flex-none rounded-[9px] border border-transparent px-[18px] py-0 text-[13.5px] font-medium text-foreground shadow-none",
  "hover:text-foreground data-active:border-border data-active:bg-card data-active:font-semibold data-active:text-foreground",
  "data-active:shadow-[0_1px_2px_rgba(41,41,39,0.06)] dark:data-active:border-border dark:data-active:bg-card",
);

export function ReportDetailPage() {
  const { batchId = "" } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [suite, setSuite] = useState<SuiteDetail | null>(null);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [simFilter, setSimFilter] = useState<"all" | "flagged">("all");
  const [badgeId, setBadgeId] = useState<string | null>(null);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [appliedFixes, setAppliedFixes] = useState<Set<string>>(() => new Set());
  const [applyOpen, setApplyOpen] = useState(false);
  const [pendingFixId, setPendingFixId] = useState<string | null>(null);
  const apply = usePromptApply(batchId);

  useEffect(() => {
    let alive = true;
    setError(null);
    setAppliedFixes(new Set());
    setApplyOpen(false);
    setPendingFixId(null);
    void client
      .evaluation(batchId)
      .then((detail) => {
        if (!alive) return;
        setRun(detail);
        if (detail.suite_id) {
          void client
            .suite(detail.suite_id)
            .then((s) => {
              if (alive) setSuite(s);
            })
            .catch(() => {
              if (alive) setSuite(null);
            });
        }
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    void client.agents().then((rows) => {
      if (alive) setAgents(rows);
    });
    return () => {
      alive = false;
    };
  }, [batchId]);

  const report = useMemo(() => {
    if (!run) return null;
    const sims = run.simulations || [];
    return buildReport({
      run,
      sims,
      index: indexSuiteScenarios(suite),
      agent: resolveAgentName(run, agents, suite, sims),
      advice: run.advice,
    });
  }, [run, suite, agents]);

  const shownRows = useMemo(() => {
    if (!report) return [];
    return simFilter === "flagged"
      ? report.rows.filter((r) => r.flagged)
      : report.rows;
  }, [report, simFilter]);

  const selectedBadge =
    report?.badges.find((b) => b.id === badgeId) || report?.badges[0] || null;

  async function share() {
    const url = `${window.location.origin}/reports/${encodeURIComponent(batchId)}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Could not copy the report link.");
    }
  }

  async function exportRun() {
    if (!report) return;
    try {
      const { downloadReportPdf } = await import("@/lib/reportPdf");
      downloadReportPdf(report);
    } catch {
      setError("Could not export the report PDF.");
    }
  }

  function downloadBadges() {
    if (!report) return;
    downloadText(
      `wiretap-badges-${report.hash}.svg`,
      badgePackSvg(report),
      "image/svg+xml",
    );
  }

  if (error && !run) {
    return (
      <div className="pb-16">
        <BackLink />
        <p className="mt-4 text-sm text-fail">{error}</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="pb-16">
        <BackLink />
        <p className="mt-4 text-sm text-muted-foreground">Loading report…</p>
      </div>
    );
  }

  const earnedCount = report.badges.filter((b) => b.met).length;

  return (
    <div className="pb-[72px]">
      <BackLink />

      <div className="mt-3.5 mb-[26px] flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1 basis-[420px]">
          <h2 className="mb-2 text-2xl font-bold leading-tight tracking-[-0.014em]">
            {report.name}
          </h2>
          <div className="font-mono text-[11.5px] leading-relaxed text-[var(--wt-text-muted)]">
            {report.suiteId} · {report.agent} · ℣-{report.hash} ·{" "}
            {formatRelative(report.createdAt)}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="rounded-full"
            onClick={() => setRerunOpen(true)}
          >
            <RefreshCw data-icon="inline-start" />
            Re-run
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded-full"
            onClick={() => void exportRun()}
          >
            <Download data-icon="inline-start" />
            Export
          </Button>
          <Button type="button" size="sm" className="rounded-full" onClick={() => void share()}>
            {copied ? (
              <Check data-icon="inline-start" />
            ) : (
              <Share2 data-icon="inline-start" />
            )}
            {copied ? "Copied" : "Share report"}
          </Button>
        </div>
      </div>

      {error && <p className="mb-4 text-sm text-fail">{error}</p>}

      <div className="grid grid-cols-1 items-start gap-8 rounded-2xl border border-border bg-card p-6 md:grid-cols-2">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
            Overall score
          </div>
          <div className="mt-3 mb-3 flex items-end gap-2.5">
            <span className="font-mono text-[60px] font-semibold leading-none tracking-[-0.03em]">
              {report.overall == null ? "—" : report.overall}
            </span>
            <span className="pb-1.5 font-mono text-[15px] text-[var(--wt-text-muted)]">
              / 100
            </span>
          </div>
          <div className="mb-[18px] flex flex-wrap items-center gap-2.5">
            <ReportStatusPill status={report.status} />
            <span className="text-[11.5px] text-[var(--wt-text-muted)]">
              90 or above ships
            </span>
          </div>
          <div className="flex flex-col">
            {[
              {
                label: "Categories covered",
                value: `${report.covered.length} of ${REPORT_CATEGORIES.length}`,
              },
              { label: "Simulations played", value: String(report.simCount) },
              {
                label: "Checks passed",
                value: `${report.passedCount} / ${report.simCount}`,
              },
              { label: "Agent", value: report.agent },
            ].map((row) => (
              <div
                key={row.label}
                className="flex items-center justify-between gap-4 border-t border-border py-2.5"
              >
                <span className="text-[12.5px] text-muted-foreground">
                  {row.label}
                </span>
                <span className="font-mono text-[12.5px] font-medium text-foreground">
                  {row.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="min-w-0">
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
              Score by category
            </div>
            <span className="font-mono text-[11.5px] text-[var(--wt-text-muted)]">
              {report.covered.length} of {REPORT_CATEGORIES.length}
            </span>
          </div>
          <div className="mb-3.5 text-xs text-muted-foreground">
            Only the categories this run was pointed at.
          </div>
          <div className="flex flex-col gap-[11px]">
            {report.covered.map((id) => {
              const v = report.scores[id] ?? 0;
              const band = scoreBand(v);
              return (
                <div
                  key={id}
                  className="grid grid-cols-[112px_1fr_42px] items-center gap-3"
                >
                  <span className="truncate text-[12.5px] text-foreground">
                    {categoryLabel(id)}
                  </span>
                  <span className="block h-1.5 overflow-hidden rounded-full bg-[var(--wt-section)]">
                    <span
                      className={cn(
                        "block h-full rounded-full",
                        band === "high" && "bg-[var(--wt-green-600)]",
                        band === "mid" && "bg-[rgba(5,105,56,0.40)]",
                        band === "low" && "bg-[var(--wt-danger)]",
                      )}
                      style={{ width: `${v}%` }}
                    />
                  </span>
                  <span
                    className={cn(
                      "text-right font-mono text-[12.5px] font-medium",
                      v >= 70 ? "text-foreground" : "text-[var(--wt-danger)]",
                    )}
                  >
                    {v}
                  </span>
                </div>
              );
            })}
            {report.covered.length === 0 && (
              <div className="text-[12.5px] text-muted-foreground">
                No category scores yet — simulations in this run have no scored
                categories.
              </div>
            )}
          </div>
          {!report.full && (
            <div className="mt-4 rounded-[10px] border border-border bg-[var(--wt-section)] px-3.5 py-[11px] text-xs leading-relaxed text-muted-foreground text-pretty">
              Not covered by this run:{" "}
              {report.missing.map(categoryLabel).join(", ")}. The score above
              averages only the {report.covered.length}{" "}
              {report.covered.length === 1 ? "category" : "categories"} that ran.
            </div>
          )}
        </div>
      </div>

      <div className="mt-10">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-6">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
              Badges
            </div>
            <div className="mt-[7px] mb-[3px] text-[17px] font-semibold">
              {report.full
                ? earnedCount
                  ? `${earnedCount} of 4 badges earned`
                  : "No badges earned from this run"
                : "Badges locked"}
            </div>
            <p className="max-w-[620px] text-[12.5px] leading-relaxed text-muted-foreground text-pretty">
              {report.full
                ? "Full coverage, so every badge was assessed. Open one to see its validity and the score it was issued against."
                : `A badge needs one run across all ${REPORT_CATEGORIES.length} categories. This run covered ${report.covered.length} — re-run with the full set to unlock them.`}
            </p>
          </div>
          {report.full && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="shrink-0 rounded-full"
              onClick={downloadBadges}
            >
              <Download data-icon="inline-start" />
              Download badge pack
            </Button>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {report.badges.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => setBadgeId(b.id)}
              className={cn(
                "flex items-center gap-3.5 rounded-[14px] border bg-card p-3.5 text-left transition-colors hover:border-[var(--wt-border-strong)] hover:bg-[var(--wt-section)]",
                b.met ? "border-primary" : "border-border",
              )}
            >
              <ReportBadgePlate badge={b} period={report.period} />
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-1.5">
                  <span className="text-[13.5px] font-semibold leading-snug">
                    {b.name}
                  </span>
                  {b.met ? (
                    <Check className="size-[13px] shrink-0 text-primary" />
                  ) : b.locked ? (
                    <Lock className="size-[13px] shrink-0 text-muted-foreground" />
                  ) : (
                    <X className="size-[13px] shrink-0 text-muted-foreground" />
                  )}
                </div>
                <div
                  className={cn(
                    "inline-flex items-center text-[11.5px] font-semibold tracking-[0.04em] uppercase",
                    b.met
                      ? "text-[var(--wt-green-700)]"
                      : "text-[var(--wt-text-muted)]",
                  )}
                >
                  {b.locked ? "Locked" : b.met ? "Earned" : "Not attained"}
                </div>
                <div className="mt-1 text-[11.5px] leading-snug text-[var(--wt-text-muted)]">
                  {b.locked
                    ? `Needs all ${REPORT_CATEGORIES.length} categories`
                    : b.met
                      ? `Valid to ${report.expires}`
                      : `Needs ${b.min}, scored ${b.value}`}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="mt-11">
        <div className="mb-3.5 flex flex-wrap items-end justify-between gap-6">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
              Simulations
            </div>
            <div className="mt-[7px] mb-[3px] flex items-baseline gap-2.5">
              <div className="text-[17px] font-semibold">
                Every simulation in this run
              </div>
              <span className="font-mono text-[12.5px] text-[var(--wt-text-muted)]">
                {report.simCount}
              </span>
            </div>
            <p className="text-[12.5px] leading-relaxed text-muted-foreground">
              One row per scenario the simulator played. Open a row for the
              transcript.
            </p>
          </div>
          <Tabs
            value={simFilter}
            onValueChange={(v) => setSimFilter(v as "all" | "flagged")}
            className="shrink-0 gap-0"
          >
            <TabsList className="box-border flex h-9 items-center gap-0.5 rounded-xl bg-[var(--wt-section)] p-[3px] text-foreground">
              <TabsTrigger value="all" className={segmentTabClass}>
                All {report.simCount}
              </TabsTrigger>
              <TabsTrigger value="flagged" className={segmentTabClass}>
                Flagged {report.flaggedCount}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <div className="grid grid-cols-[minmax(0,1.5fr)_minmax(0,1.7fr)_84px_minmax(0,1.6fr)_108px] gap-3.5 border-b border-border bg-[var(--wt-section)] px-[18px] py-[13px]">
            {["Test", "Expected outcome", "Result", "Suggested fix"].map((h) => (
              <div
                key={h}
                className="text-[10.5px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase"
              >
                {h}
              </div>
            ))}
            <div className="text-right text-[10.5px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
              Action
            </div>
          </div>
          {shownRows.length === 0 && (
            <div className="px-[18px] py-10 text-center text-[13px] text-muted-foreground">
              {report.simCount === 0
                ? "This run has no saved simulations."
                : "No flagged simulations in this run."}
            </div>
          )}
          {shownRows.map((row, i) => {
            const sim = row.simulation;
            const to = `/evaluations/${encodeURIComponent(report.batchId)}/scenarios/${encodeURIComponent(sim.simulation_id)}`;
            const pass = !row.flagged;
            const applied = appliedFixes.has(sim.simulation_id);
            const findingIds = promptFindingIdsForScenario(
              run?.advice?.findings,
              sim.scenario_id,
            );
            const canApply = !pass && !applied && findingIds.length > 0;
            return (
              <div
                key={sim.simulation_id}
                role="link"
                tabIndex={0}
                onClick={() => navigate(to)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    navigate(to);
                  }
                }}
                className={cn(
                  "grid cursor-pointer grid-cols-[minmax(0,1.5fr)_minmax(0,1.7fr)_84px_minmax(0,1.6fr)_108px] items-start gap-3.5 px-[18px] py-3.5 transition-colors hover:bg-[var(--wt-section)]",
                  i > 0 && "border-t border-border",
                )}
              >
                <div className="min-w-0">
                  <div className="text-[13.5px] font-medium leading-snug text-pretty">
                    {sim.scenario_name || sim.scenario_id}
                  </div>
                  <div className="mt-[7px] flex min-w-0 items-center gap-2">
                    <span className="inline-block max-w-full truncate rounded-full border border-border bg-[var(--wt-section)] px-[9px] py-[3px] text-[11.5px] leading-snug text-muted-foreground">
                      {row.categoryLabel}
                    </span>
                    <span className="font-mono text-[11px] text-[var(--wt-text-muted)]">
                      {sim.simulation_id.slice(0, 12)}
                    </span>
                  </div>
                </div>
                <div className="text-[12.5px] leading-relaxed text-muted-foreground text-pretty">
                  {row.expected}
                </div>
                <div>
                  <span
                    className={cn(
                      "inline-flex min-w-11 items-center justify-center rounded-full border px-2.5 py-[3px] font-mono text-[12.5px] font-semibold",
                      pass
                        ? "border-primary bg-[var(--wt-green-100)] text-[var(--wt-green-700)]"
                        : "border-[var(--wt-danger)] bg-[var(--wt-danger-surface)] text-[var(--wt-danger)]",
                    )}
                  >
                    {row.score == null ? "—" : row.score}
                  </span>
                </div>
                <div
                  className={cn(
                    "text-[12.5px] leading-relaxed text-pretty",
                    row.fix
                      ? "text-muted-foreground"
                      : "text-[var(--wt-text-muted)]",
                  )}
                >
                  {row.fix || "—"}
                </div>
                <div className="flex justify-end">
                  {canApply ? (
                    <Button
                      type="button"
                      size="sm"
                      className="h-auto rounded-full px-3.5 py-1.5 text-xs font-semibold"
                      disabled={apply.busy}
                      onClick={(e) => {
                        e.stopPropagation();
                        setPendingFixId(sim.simulation_id);
                        setApplyOpen(true);
                        void apply.openPreview(findingIds);
                      }}
                    >
                      Apply fix
                    </Button>
                  ) : applied ? (
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[11.5px] font-semibold text-[var(--wt-green-700)]">
                      <Check className="size-3" />
                      Applied
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <ApplyPromptDialog
        open={applyOpen}
        onOpenChange={(open) => {
          if (!open) {
            apply.close();
            setApplyOpen(false);
            setPendingFixId(null);
          }
        }}
        preview={apply.preview}
        busy={apply.busy}
        error={apply.error}
        onConfirm={() => {
          void (async () => {
            if (!(await apply.confirmApply()) || !pendingFixId) return;
            setAppliedFixes((prev) => {
              const next = new Set(prev);
              next.add(pendingFixId);
              return next;
            });
            setApplyOpen(false);
            setPendingFixId(null);
          })();
        }}
      />

      <BadgeModal
        open={!!badgeId}
        onOpenChange={(open) => {
          if (!open) setBadgeId(null);
        }}
        report={report}
        badge={selectedBadge}
        onCta={() => {
          if (!selectedBadge) return;
          if (selectedBadge.locked) {
            setBadgeId(null);
            if (report.suiteId) navigate(`/suites/${encodeURIComponent(report.suiteId)}`);
            return;
          }
          if (selectedBadge.met) {
            downloadBadges();
            return;
          }
          setBadgeId(null);
          setRerunOpen(true);
        }}
      />

      <NewRunDialog
        open={rerunOpen}
        onOpenChange={setRerunOpen}
        initialSuite={report.suiteId || null}
      />
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to="/reports"
      className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12.5px] font-medium text-muted-foreground transition-colors hover:bg-[var(--wt-section)] hover:text-foreground"
    >
      <ChevronLeft className="size-3.5" />
      Reports
    </Link>
  );
}

function BadgeModal({
  open,
  onOpenChange,
  report,
  badge,
  onCta,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: ReportView;
  badge: ReportBadge | null;
  onCta: () => void;
}) {
  if (!badge) return null;
  const ctaLabel = badge.locked
    ? `Run all ${REPORT_CATEGORIES.length} categories`
    : badge.met
      ? "Download badge"
      : "Re-run this suite";
  const note = badge.locked
    ? `Badges are issued from full-coverage runs only. This run covered ${report.covered.length} of ${REPORT_CATEGORIES.length} categories, so nothing can be certified yet — point the suite at every category and re-run.`
    : badge.met
      ? "Embed it on your site or drop it in a security review. The badge links back to this report, so anyone can see the run behind it."
      : "You ran full coverage, so this badge is live — the score just came in under the bar. Fix the flagged checks below and re-run to claim it.";
  const statusLabel = badge.locked
    ? "Locked"
    : badge.met
      ? `Earned · ${report.issued}`
      : "Not attained";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="max-w-[520px] rounded-[18px] border-border p-[26px] sm:max-w-[520px]"
      >
        <div className="mb-[22px] flex items-start justify-between gap-4">
          <DialogTitle className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
            Badge
          </DialogTitle>
          <button
            type="button"
            aria-label="Close"
            onClick={() => onOpenChange(false)}
            className="-mt-1 -mr-1 rounded-lg p-1 text-muted-foreground hover:bg-[var(--wt-section)] hover:text-foreground"
          >
            <X className="size-[15px]" />
          </button>
        </div>
        <div className="flex flex-wrap items-start gap-[26px]">
          <ReportBadgePlate badge={badge} period={report.period} size="lg" />
          <div className="min-w-[220px] flex-1">
            <div className="mb-1.5 text-[17px] font-semibold leading-snug">
              {badge.name}
            </div>
            <div
              className={cn(
                "inline-flex items-center text-[11.5px] font-semibold tracking-[0.04em] uppercase",
                badge.met
                  ? "text-[var(--wt-green-700)]"
                  : "text-[var(--wt-text-muted)]",
              )}
            >
              {statusLabel}
            </div>
            <div className="mt-4 flex flex-col">
              {[
                {
                  label: badge.cat ? `${categoryLabel(badge.cat)} score` : "Overall score",
                  value:
                    badge.locked || badge.value == null
                      ? "Not measured"
                      : String(badge.value),
                },
                { label: "Criteria", value: badge.crit },
                { label: "Issued", value: badge.met ? report.issued : "—" },
                { label: "Valid through", value: badge.met ? report.expires : "—" },
                { label: "From run", value: report.name },
              ].map((row) => (
                <div
                  key={row.label}
                  className="flex items-center justify-between gap-4 border-t border-border py-[9px]"
                >
                  <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
                    {row.label}
                  </span>
                  <span
                    className={cn(
                      "text-right text-xs font-medium text-foreground",
                      row.label === "Criteria"
                        ? "max-w-[210px] leading-snug font-normal"
                        : "font-mono",
                    )}
                  >
                    {row.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-5 text-[12.5px] leading-relaxed text-muted-foreground text-pretty">
          {note}
        </div>
        <div className="mt-[22px] flex items-center justify-end gap-2 border-t border-border pt-[18px]">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="rounded-full"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
          <Button type="button" size="sm" className="rounded-full" onClick={onCta}>
            {ctaLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
