import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Check,
  ChevronDown,
  ChevronsLeftRight,
  Copy,
  FileText,
  FlaskConical,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  ApplyPromptDialog,
  isPromptFinding,
  usePromptApply,
} from "@/components/ApplyPromptDialog";
import { CallAudioPlayer, formatClock, buildSpeechSegments, activeSegmentIndex, hasRealTimings, type TimedTurn } from "@/components/CallAudioPlayer";
import { TruncatedText } from "@/components/TruncatedText";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  client,
  type AdviceFinding,
  type RunAdvice,
  type Simulation,
  type ToolCall,
} from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatGoalPct, simulationVerdict } from "@/lib/format";
import { cn } from "@/lib/utils";

const TARGET_LABELS: Record<string, string> = {
  agent_prompt: "Prompt",
  tools: "Tools",
  flow: "Flow",
  voice_runtime: "Voice config",
  test_suite: "Test suite",
};

function formatToolArgs(args: Record<string, unknown> | undefined): string {
  const entries = Object.entries(args ?? {});
  if (!entries.length) return "{}";
  const parts = entries.map(([k, v]) => {
    let rendered: string;
    try {
      rendered = JSON.stringify(v);
    } catch {
      rendered = String(v);
    }
    return `${k}: ${rendered}`;
  });
  return `{ ${parts.join(", ")} }`;
}

function formatToolOut(summary: string | undefined): string {
  const s = (summary || "").trim();
  return s || "—";
}

/** Matches Wiretap.dc.html tool-call card in the transcript stream. */
function ToolRow({
  call,
  active,
  onSeek,
}: {
  call: ToolCall;
  active?: boolean;
  onSeek?: () => void;
}) {
  const ok = call.status === "ok";
  const errored = call.status === "error";
  const statusLabel = ok ? "ok" : errored ? "error" : call.status || "unknown";
  const clock =
    call.at_seconds != null && Number.isFinite(call.at_seconds)
      ? formatClock(call.at_seconds)
      : null;

  return (
    <div className="flex items-start gap-3">
      <button
        type="button"
        disabled={!onSeek && clock == null}
        className={cn(
          "mt-2.5 w-[38px] shrink-0 bg-transparent text-right font-mono text-[11.5px] transition-colors",
          active
            ? "text-[var(--wt-green-700)]"
            : "text-[var(--wt-text-muted)] hover:text-foreground",
          !onSeek && "cursor-default hover:text-[var(--wt-text-muted)]",
        )}
        onClick={onSeek}
      >
        {clock ?? "—"}
      </button>
      <div
        className={cn(
          "min-w-0 flex-1 rounded-xl border px-4 py-3",
          "border-border bg-[var(--wt-section)]",
          active && "border-[var(--wt-green-600)]",
        )}
      >
        <div className="flex items-center gap-2.5">
          <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-[7px] border border-border bg-card text-muted-foreground">
            <ChevronsLeftRight className="size-3" strokeWidth={1.9} />
          </span>
          <span className="min-w-0 truncate font-mono text-[12.5px] font-medium text-foreground">
            {call.name}
          </span>
          <span
            className={cn(
              "inline-flex shrink-0 items-center rounded-full border bg-card px-2 py-0.5 font-mono text-[10.5px] font-semibold tracking-[0.04em] uppercase",
              errored
                ? "border-[var(--wt-danger)] text-[var(--wt-danger)]"
                : "border-border text-muted-foreground",
            )}
          >
            {statusLabel}
          </span>
        </div>
        <div className="mt-2.5 ml-[34px] flex flex-col gap-1 font-mono text-[11.5px] leading-snug break-words text-muted-foreground">
          <div>
            <span className="text-[var(--wt-text-muted)]">args </span>
            <span className="text-foreground/80">
              {formatToolArgs(call.arguments)}
            </span>
          </div>
          <div>
            <span className="text-[var(--wt-text-muted)]">out&nbsp;&nbsp;</span>
            <span className="text-foreground/80">
              {formatToolOut(call.result_summary)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

const SEVERITY_VARIANT: Record<string, "fail" | "warn" | "muted"> = {
  high: "fail",
  medium: "warn",
  low: "muted",
};

const segmentTabClass = cn(
  "box-border h-[30px] flex-none rounded-[9px] border border-transparent px-[18px] py-0 text-[13.5px] font-medium text-foreground shadow-none",
  "hover:text-foreground data-active:border-border data-active:bg-card data-active:font-semibold data-active:text-foreground",
  "data-active:shadow-[0_1px_2px_rgba(41,41,39,0.06)] dark:data-active:border-border dark:data-active:bg-card",
);

const fieldLabelClass =
  "text-[10.5px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase";

const WRITABLE_PLATFORMS = new Set(["retell", "vapi", "elevenlabs"]);

function findingKey(finding: AdviceFinding, index: number) {
  return finding.id || `${finding.title}-${index}`;
}

function FindingCard({
  finding,
  index,
  selectable,
  selected,
  onToggle,
}: {
  finding: AdviceFinding;
  index: number;
  selectable: boolean;
  selected: boolean;
  onToggle: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const evidence = finding.evidence ?? [];
  const affected = finding.affected_scenarios ?? [];
  const severity = String(finding.severity ?? "medium").toLowerCase();

  const copy = async () => {
    await navigator.clipboard.writeText(finding.suggested_text ?? "");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <article className="rounded-[14px] border border-border bg-card px-5 py-4.5">
      <div className="flex items-start gap-3">
        {selectable && (
          <Checkbox
            checked={selected}
            onCheckedChange={() => onToggle()}
            className="mt-1"
            aria-label={`Include ${finding.title} in the prompt update`}
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <Badge
                  variant={SEVERITY_VARIANT[severity] ?? "warn"}
                  className="h-auto rounded-full px-2 py-0.5 text-[10.5px] font-semibold capitalize"
                >
                  {severity}
                </Badge>
                <Badge
                  variant="outline"
                  className="h-auto rounded-full px-2 py-0.5 text-[10.5px]"
                >
                  {TARGET_LABELS[finding.target] ?? "Agent"}
                </Badge>
                {affected.length > 1 && (
                  <span className="text-[11.5px] text-muted-foreground">
                    Affects {affected.length} calls in this run
                  </span>
                )}
              </div>
              <h3 className="text-[14.5px] leading-snug font-semibold text-pretty break-words">
                {finding.title}
              </h3>
            </div>
            <span className="shrink-0 pt-0.5 font-mono text-[11px] text-[var(--wt-text-muted)]">
              {String(index + 1).padStart(2, "0")}
            </span>
          </div>

          {finding.problem && (
            <div className="mt-3.5">
              <div className={fieldLabelClass}>What happened</div>
              <p className="mt-1 text-[13px] leading-relaxed text-pretty break-words">
                {finding.problem}
              </p>
            </div>
          )}

          {finding.recommendation && (
            <div className="mt-3.5">
              <div className={fieldLabelClass}>What to change</div>
              <p className="mt-1 text-[13px] leading-relaxed text-pretty break-words">
                {finding.recommendation}
              </p>
            </div>
          )}

          {finding.suggested_text && (
            <div className="mt-4 rounded-[12px] border border-border bg-[var(--wt-section)] p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className={fieldLabelClass}>Suggested prompt wording</div>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 rounded-full px-2.5 text-[12px]"
                  onClick={() => void copy()}
                >
                  {copied ? (
                    <Check data-icon="inline-start" />
                  ) : (
                    <Copy data-icon="inline-start" />
                  )}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <p className="rounded-[9px] border border-border bg-card px-3 py-2.5 font-mono text-[12px] leading-relaxed text-pretty break-words">
                {finding.suggested_text}
              </p>
            </div>
          )}

          {evidence.length > 0 && (
            <div className="mt-3.5">
              <button
                type="button"
                onClick={() => setShowEvidence(!showEvidence)}
                className="text-[12px] font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {showEvidence ? "Hide evidence" : `Evidence (${evidence.length})`}
              </button>
              {showEvidence && (
                <ul className="mt-2 space-y-2">
                  {evidence.map((item, i) => (
                    <li
                      key={`${item.scenario_id}-${i}`}
                      className="border-l-2 border-border pl-3"
                    >
                      <p className="text-[12.5px] leading-relaxed text-pretty break-words">
                        “{item.quote}”
                      </p>
                      {item.scenario_id && (
                        <p className="mt-0.5 font-mono text-[11px] text-[var(--wt-text-muted)]">
                          {item.scenario_id}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function ImprovementsPanel({
  advice,
  findings,
  scoped,
  batchId,
  platform,
}: {
  advice: RunAdvice | null;
  findings: AdviceFinding[];
  scoped: boolean;
  batchId: string;
  platform?: string | null;
}) {
  const promptIds = useMemo(
    () => findings.filter(isPromptFinding).map((f) => f.id).filter(Boolean),
    [findings],
  );
  const idsKey = promptIds.join("\0");
  const [selected, setSelected] = useState<Set<string>>(() => new Set(promptIds));
  const [applied, setApplied] = useState(false);
  const apply = usePromptApply(batchId);

  // Only re-select when the finding *ids* change. Advice polling rebuilds
  // `findings` every few seconds; wiping preview there closed the modal.
  useEffect(() => {
    setSelected(new Set(idsKey ? idsKey.split("\0") : []));
  }, [idsKey]);

  const selectedIds = promptIds.filter((id) => selected.has(id));
  const writable = WRITABLE_PLATFORMS.has(String(platform || "").toLowerCase());
  const canApply = Boolean(batchId) && selectedIds.length > 0 && writable && !applied;

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const openPreview = async () => {
    const ids = findings
      .filter((f) => isPromptFinding(f) && selected.has(f.id))
      .map((f) => f.id);
    await apply.openPreview(ids);
  };

  const confirmApply = async () => {
    if (await apply.confirmApply()) setApplied(true);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain pr-2 pb-8">
      <div className="rounded-[14px] border border-border bg-[var(--wt-section)] px-5 py-4">
        <p className="text-[13px] leading-relaxed text-pretty">
          {scoped
            ? "Changes to the agent that would fix this call."
            : "Themes from this run. None of them name this call specifically."}
        </p>
        {advice?.summary && (
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground text-pretty break-words">
            {advice.summary}
          </p>
        )}
        <p className="mt-2 text-[11.5px] text-muted-foreground">
          {advice?.grounding === "behavior_only"
            ? "Based on call behavior only — import this agent for config-aware advice."
            : "Based on this run's failures and the agent's imported configuration."}
        </p>
      </div>
      {findings.map((finding, i) => {
        const key = finding.id || findingKey(finding, i);
        return (
          <FindingCard
            key={key}
            finding={finding}
            index={i}
            selectable={isPromptFinding(finding) && Boolean(finding.id)}
            selected={selected.has(finding.id)}
            onToggle={() => finding.id && toggle(finding.id)}
          />
        );
      })}
      {promptIds.length > 0 && (
        <div className="sticky bottom-0 rounded-[14px] border border-border bg-card px-5 py-4">
          {applied ? (
            <p className="text-[13px] text-pass">
              Live prompt updated with the selected wording.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[12.5px] text-muted-foreground">
                  {writable
                    ? `${selectedIds.length} selected — applied together as one prompt write.`
                    : "This platform has no prompt write API. Copy wording into the agent instead."}
                </p>
                <Button
                  size="sm"
                  className="rounded-full"
                  disabled={!canApply || apply.busy}
                  onClick={() => void openPreview()}
                >
                  <Sparkles data-icon="inline-start" />
                  {apply.busy && !apply.preview
                    ? "Loading prompt…"
                    : `Apply ${selectedIds.length} to prompt`}
                </Button>
              </div>
              {apply.error && !apply.preview && (
                <p className="mt-2 text-[12.5px] text-fail break-words">{apply.error}</p>
              )}
            </>
          )}
        </div>
      )}

      <ApplyPromptDialog
        open={Boolean(apply.preview)}
        onOpenChange={(open) => {
          if (!open) apply.close();
        }}
        preview={apply.preview}
        busy={apply.busy}
        error={apply.error}
        onConfirm={() => void confirmApply()}
      />
    </div>
  );
}

export function SimulationDetailPage() {
  const navigate = useNavigate();
  const { simulationId = "", batchId = "" } = useParams();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [advice, setAdvice] = useState<RunAdvice | null>(null);
  const [view, setView] = useState<"transcript" | "improvements">("transcript");
  const [error, setError] = useState<string | null>(null);
  const [activeTurn, setActiveTurn] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [showTools, setShowTools] = useState(true);
  const [audioDuration, setAudioDuration] = useState(0);
  const [seekRequest, setSeekRequest] = useState<{ sec: number; token: number } | null>(
    null,
  );

  useEffect(() => {
    client
      .simulation(simulationId)
      .then(setSim)
      .catch((e: Error) => setError(e.message));
  }, [simulationId]);

  const title = useMemo(() => {
    if (!sim) return "Scenario";
    return sim.scenario_name || sim.scenario_id || "Scenario";
  }, [sim]);

  // turn_index counts turns that preceded a call, so it renders *before* that turn.
  const tools = useMemo(() => {
    const byTurn = new Map<number, ToolCall[]>();
    const unplaced: ToolCall[] = [];
    const total = sim?.transcript.length ?? 0;
    for (const call of sim?.tool_calls ?? []) {
      const at = call.turn_index;
      if (at === null || at === undefined || at < 0 || at > total) {
        unplaced.push(call);
        continue;
      }
      byTurn.set(at, [...(byTurn.get(at) ?? []), call]);
    }
    return { byTurn, unplaced, total };
  }, [sim]);

  const toolSummary = useMemo(() => {
    if (!sim || sim.meta?.tool_capture !== "ok") return null;
    const missing = (sim.metrics?.missing_tools as string[] | undefined) ?? [];
    const parts = [`${(sim.tool_calls ?? []).length} called`];
    if (missing.length > 0) parts.push(`${missing.join(", ")} never called`);
    return `Tools: ${parts.join(" · ")}`;
  }, [sim]);

  const audioSrc = sim?.audio_path
    ? `/api/simulations/${simulationId}/audio`
    : null;

  const backBatch = batchId || sim?.batch_id || "";
  const backTo = backBatch
    ? `/evaluations?run=${encodeURIComponent(backBatch)}`
    : "/evaluations";

  // Advice is generated after each failed judgement, so it lives on the parent
  // evaluation and can appear before the rest of the suite finishes.
  useEffect(() => {
    if (!backBatch) return;
    let cancelled = false;
    const load = () =>
      client
        .evaluation(backBatch)
        .then((run) => {
          if (!cancelled) setAdvice(run.advice ?? null);
        })
        .catch(() => {
          if (!cancelled) setAdvice(null);
        });
    void load();
    const tick = window.setInterval(() => void load(), 4000);
    return () => {
      cancelled = true;
      window.clearInterval(tick);
    };
  }, [backBatch]);

  const findings = useMemo(() => {
    const all = advice?.findings ?? [];
    if (!sim || all.length === 0) return { items: [] as AdviceFinding[], scoped: true };
    const mine = all.filter((f) =>
      (f.affected_scenarios ?? []).includes(sim.scenario_id),
    );
    if (mine.length > 0) return { items: mine, scoped: true };
    // Nothing named this call: show the run's themes rather than an empty card,
    // but only where there is a failure to explain.
    return { items: sim.passed ? [] : all.slice(0, 2), scoped: false };
  }, [advice, sim]);

  const turnCount = sim?.transcript?.length || 0;
  const toolCount = sim?.tool_calls?.length ?? 0;
  const agentLabel =
    (sim?.meta?.agent_name as string | undefined) ||
    (sim?.meta?.agent_id as string | undefined) ||
    "Agent";
  const callerLabel = sim?.persona_name || "Caller";
  const verdict = useMemo(
    () => (sim ? simulationVerdict(sim) : null),
    [sim],
  );
  const statusLabel = verdict?.label ?? "—";

  const timedTurns = useMemo((): TimedTurn[] => {
    if (!sim) return [];
    const transcript = (sim.transcript || []) as TimedTurn[];
    // 1) Provider / live clocks already on the displayed transcript.
    if (hasRealTimings(transcript)) return transcript;
    // 2) CallRecorder WAV offsets saved at sim time.
    const playback = sim.meta?.playback_turns;
    if (Array.isArray(playback) && hasRealTimings(playback as TimedTurn[])) {
      const pb = playback as TimedTurn[];
      if (pb.length === transcript.length && transcript.length > 0) {
        return transcript.map((t, i) => ({
          ...t,
          start_ms: pb[i]?.start_ms,
          end_ms: pb[i]?.end_ms,
        }));
      }
      return pb;
    }
    // 3) buildSpeechSegments will estimate from text length.
    return transcript;
  }, [sim]);

  const segments = useMemo(() => {
    if (!sim || !audioDuration) return [];
    // Real WAV offsets when present; otherwise estimate from transcript text length.
    return buildSpeechSegments(
      timedTurns.length ? timedTurns : sim.transcript,
      audioDuration,
    );
  }, [sim, timedTurns, audioDuration]);

  const failBelow = sim?.judge?.fail_below ?? 0.5;
  const passAt = sim?.judge?.pass_at ?? 0.7;
  const goalPctLabel =
    formatGoalPct(sim?.judge?.score ?? null) !== "—"
      ? formatGoalPct(sim?.judge?.score ?? null)
      : typeof sim?.meta?.goal_match_pct === "number"
        ? `${Math.round(Number(sim.meta.goal_match_pct))}%`
        : "—";

  async function rerun(mode: "fresh" | "same") {
    if (!sim?.suite_id) return;
    setBusy(true);
    setError(null);
    try {
      const { batch_id } = await client.startBatch({
        suite: sim.suite_id,
        all: mode === "fresh",
        scenario: mode === "same" ? sim.scenario_id : undefined,
        concurrency: 4,
      });
      navigate(`/batches/${batch_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onPlayerTime(t: number) {
    setActiveTurn(activeSegmentIndex(segments, t));
  }

  function jumpToTurn(i: number) {
    const seg = segments.find((s) => s.turnIndex === i) ?? segments[i];
    if (!seg) {
      setActiveTurn(i);
      return;
    }
    setActiveTurn(i);
    setSeekRequest((prev) => ({
      sec: seg.start,
      token: (prev?.token ?? 0) + 1,
    }));
  }

  function jumpToSeconds(sec: number) {
    setSeekRequest((prev) => ({
      sec,
      token: (prev?.token ?? 0) + 1,
    }));
  }

  if (!sim && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="-mx-8 -my-6 flex h-[calc(100dvh-1rem)] min-h-[520px] flex-col overflow-hidden">
      <header className="shrink-0 border-b border-border px-8 pt-2.5 pb-4">
        <Link
          to={backTo}
          className="-ml-2 mb-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <span aria-hidden className="text-[14px] leading-none">
            ‹
          </span>
          All simulations
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0 flex-1 basis-[420px]">
            <div className="mb-1.5 flex min-w-0 flex-wrap items-center gap-2.5">
              <h1 className="min-w-0 max-w-full">
                <TruncatedText
                  as="span"
                  text={title}
                  className="text-[21px] font-bold tracking-[-0.012em] text-foreground"
                />
              </h1>
              {sim && verdict && (
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
                    verdict.variant === "pass" &&
                      "border-[var(--wt-green-600)] bg-[var(--wt-green-100)] text-[var(--wt-green-700)]",
                    verdict.variant === "warn" &&
                      "border-warn bg-[var(--wt-section)] text-foreground",
                    verdict.variant === "fail" && "border-fail text-fail",
                  )}
                >
                  <span
                    className={cn(
                      "size-[7px] rounded-full",
                      verdict.variant === "pass" && "bg-pass",
                      verdict.variant === "warn" && "bg-warn",
                      verdict.variant === "fail" && "bg-fail",
                    )}
                  />
                  {statusLabel}
                  {verdict.pct != null ? (
                    <span className="font-mono font-medium tabular-nums opacity-80">
                      {verdict.pct}%
                    </span>
                  ) : null}
                </span>
              )}
            </div>
            {sim && (
              <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-muted-foreground">
                <span className="shrink-0">Agent tested</span>
                <TruncatedText
                  text={agentLabel}
                  className="max-w-[min(280px,40vw)] font-medium text-[var(--wt-text-secondary)]"
                />
                <span className="shrink-0 text-border">·</span>
                <span className="shrink-0">persona</span>
                <TruncatedText
                  text={callerLabel}
                  className="max-w-[min(200px,30vw)] font-medium text-[var(--wt-text-secondary)]"
                />
                {sim.simulation_id && (
                  <>
                    <span className="shrink-0 text-border">·</span>
                    <TruncatedText
                      text={sim.simulation_id}
                      className="max-w-[140px] font-mono text-[11.5px] text-[var(--wt-text-muted)]"
                    />
                  </>
                )}
              </div>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {sim?.suite_id && (
              <Button variant="outline" size="sm" className="rounded-full" asChild>
                <Link to={`/suites/${encodeURIComponent(sim.suite_id)}`}>
                  <FlaskConical data-icon="inline-start" />
                  Test scenario
                </Link>
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-full"
                  disabled={busy || !sim?.suite_id}
                >
                  <RefreshCw data-icon="inline-start" />
                  Re-run
                  <ChevronDown data-icon="inline-end" className="opacity-70" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuItem
                  className="flex flex-col items-start gap-0.5 py-2.5"
                  onClick={() => void rerun("fresh")}
                >
                  <span className="font-semibold">Fresh run</span>
                  <span className="text-xs text-muted-foreground text-pretty">
                    Builds new test calls from the scenario as configured today.
                  </span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="flex flex-col items-start gap-0.5 py-2.5"
                  onClick={() => void rerun("same")}
                >
                  <span className="font-semibold">Re-run with same data</span>
                  <span className="text-xs text-muted-foreground text-pretty">
                    Replays this call&apos;s scenario — same persona and settings.
                  </span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              size="sm"
              className="rounded-full"
              asChild={Boolean(backBatch)}
              disabled={!backBatch}
              onClick={
                backBatch
                  ? undefined
                  : () => {
                      document
                        .getElementById("sim-verdict")
                        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                    }
              }
            >
              {backBatch ? (
                <Link to={`/reports/${encodeURIComponent(backBatch)}`}>
                  <FileText data-icon="inline-start" />
                  View report
                </Link>
              ) : (
                <>
                  <FileText data-icon="inline-start" />
                  View report
                </>
              )}
            </Button>
          </div>
        </div>
      </header>

      {error && (
        <p className="shrink-0 px-8 pt-3 text-sm text-fail">{error}</p>
      )}

      {sim && (
        <div className="flex min-h-0 flex-1 justify-center overflow-hidden px-8 pt-5">
          <div className="flex min-h-0 w-full max-w-[1148px] gap-7">
            <div className="flex min-h-0 min-w-0 max-w-[820px] flex-1 flex-col">
              <div className="mb-3.5 flex shrink-0 flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-baseline gap-2.5">
                  {findings.items.length > 0 ? (
                    <Tabs
                      value={view}
                      onValueChange={(v) =>
                        setView(v as "transcript" | "improvements")
                      }
                      className="gap-0"
                    >
                      <TabsList className="box-border flex h-9 items-center gap-0.5 rounded-xl bg-[var(--wt-section)] p-[3px] text-foreground">
                        <TabsTrigger value="transcript" className={segmentTabClass}>
                          Transcript
                        </TabsTrigger>
                        <TabsTrigger
                          value="improvements"
                          className={segmentTabClass}
                        >
                          Improvements
                          <Badge
                            variant={view === "improvements" ? "default" : "muted"}
                            className="ml-1.5 h-[18px] min-w-[18px] rounded-full px-1.5 text-[10.5px]"
                          >
                            {findings.items.length}
                          </Badge>
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                  ) : (
                    <h2 className="shrink-0 text-[15px] font-semibold">
                      Transcript
                    </h2>
                  )}
                  {view === "transcript" && (
                    <span className="font-mono text-xs text-[var(--wt-text-muted)]">
                      {turnCount} turns
                      {toolCount > 0 ? ` · ${toolCount} tool calls` : ""}
                    </span>
                  )}
                </div>
                {view === "transcript" && toolCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowTools((v) => !v)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] font-medium transition-colors",
                      showTools
                        ? "border-[var(--wt-green-600)] bg-[var(--wt-green-100)] text-[var(--wt-green-700)]"
                        : "border-border bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <ChevronsLeftRight className="size-3" strokeWidth={1.9} />
                    Tool calls
                  </button>
                )}
              </div>

              {view === "improvements" && findings.items.length > 0 && (
                <ImprovementsPanel
                  advice={advice}
                  findings={findings.items}
                  scoped={findings.scoped}
                  batchId={backBatch}
                  platform={
                    (sim.meta?.platform as string | undefined) || null
                  }
                />
              )}

              <div
                hidden={view !== "transcript"}
                className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain pr-2 pb-8"
              >
                {sim.transcript.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Empty transcript.
                  </p>
                ) : (
                  sim.transcript.map((t, i) => {
                    const isCaller = t.role === "user" || t.role === "caller";
                    const seg = segments.find((s) => s.turnIndex === i);
                    const start = seg?.start;
                    const end = seg?.end;
                    const active = activeTurn === i;
                    const speaker = isCaller ? callerLabel : agentLabel;
                    const showClock = start != null && end != null;
                    return (
                      <div key={`${t.role}-${i}`} className="space-y-2.5">
                        {showTools &&
                          (tools.byTurn.get(i) ?? []).map((call, n) => (
                            <ToolRow
                              key={`${call.name}-${i}-${n}`}
                              call={call}
                              onSeek={
                                call.at_seconds != null
                                  ? () => jumpToSeconds(call.at_seconds!)
                                  : undefined
                              }
                            />
                          ))}
                        <div className="flex items-start gap-3">
                        <button
                          type="button"
                          className={cn(
                            "mt-3 w-[38px] shrink-0 bg-transparent text-right font-mono text-[11.5px] transition-colors",
                            active
                              ? "text-[var(--wt-green-700)]"
                              : "text-[var(--wt-text-muted)] hover:text-foreground",
                          )}
                          onClick={() => jumpToTurn(i)}
                        >
                          {showClock ? formatClock(start) : String(i + 1).padStart(2, "0")}
                        </button>
                        <button
                          type="button"
                          className={cn(
                            "min-w-0 flex-1 overflow-hidden rounded-[14px] px-4 py-3 text-left transition-colors",
                            isCaller
                              ? "border border-[#F2F1EE] bg-[#F2F1EE]"
                              : "border border-border bg-card",
                            active && "border-[var(--wt-green-600)]",
                          )}
                          onClick={() => jumpToTurn(i)}
                        >
                          <div className="mb-1 flex min-w-0 items-center gap-2">
                            <span
                              className={cn(
                                "size-[7px] shrink-0 rounded-full",
                                isCaller
                                  ? "bg-[#A7A7A5]"
                                  : "bg-[var(--wt-green-600)]",
                              )}
                            />
                            <TruncatedText
                              text={speaker}
                              className="max-w-[min(100%,280px)] text-xs font-semibold"
                            />
                            {showClock && (
                              <span className="ml-auto shrink-0 font-mono text-[11px] text-[var(--wt-text-muted)]">
                                {formatClock(start)} — {formatClock(end)}
                              </span>
                            )}
                          </div>
                          <div className="text-[13.5px] leading-relaxed text-pretty break-words">
                            {t.text}
                          </div>
                        </button>
                        </div>
                      </div>
                    );
                  })
                )}
                {showTools &&
                  (tools.byTurn.get(tools.total) ?? []).map((call, n) => (
                    <ToolRow
                      key={`tail-${call.name}-${n}`}
                      call={call}
                      onSeek={
                        call.at_seconds != null
                          ? () => jumpToSeconds(call.at_seconds!)
                          : undefined
                      }
                    />
                  ))}
                {showTools && tools.unplaced.length > 0 && (
                  <div className="space-y-2.5 pt-1">
                    <p className="pl-[50px] text-[12px] text-muted-foreground">
                      Tool calls with no known position in the transcript:
                    </p>
                    {tools.unplaced.map((call, n) => (
                      <ToolRow
                        key={`unplaced-${call.name}-${n}`}
                        call={call}
                        onSeek={
                          call.at_seconds != null
                            ? () => jumpToSeconds(call.at_seconds!)
                            : undefined
                        }
                      />
                    ))}
                  </div>
                )}
                {typeof sim.meta?.tool_capture === "string" &&
                  sim.meta.tool_capture !== "ok" && (
                  <p className="pt-1 text-[12px] text-muted-foreground">
                    Tool calls not observable for this agent.
                  </p>
                )}
              </div>
            </div>

            <aside className="flex min-h-0 w-full max-w-[320px] min-w-[230px] shrink-0 basis-[300px] flex-col gap-3.5 overflow-y-auto overscroll-contain pb-10">
              <div className="min-w-0 shrink-0 rounded-[14px] border border-border bg-card px-5 py-5">
                <div className="mb-3 text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
                  Goal match
                </div>
                <div className="flex items-end justify-between gap-3">
                  <div
                    className={cn(
                      "font-mono text-[28px] font-semibold leading-none tabular-nums",
                      verdict?.variant === "pass" && "text-pass",
                      verdict?.variant === "warn" && "text-warn",
                      verdict?.variant === "fail" && "text-fail",
                      !verdict && "text-muted-foreground",
                    )}
                  >
                    {goalPctLabel}
                  </div>
                  <span className="pb-0.5 text-[12.5px] font-medium text-muted-foreground">
                    {verdict?.label === "Inconclusive"
                      ? "No score"
                      : verdict?.label ?? "—"}
                  </span>
                </div>
                <div className="mt-4 space-y-1.5 text-[11.5px] leading-snug text-muted-foreground">
                  <div className="flex justify-between gap-2">
                    <span>Fail</span>
                    <span className="font-mono tabular-nums">
                      &lt; {Math.round(failBelow * 100)}%
                    </span>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span>Partial</span>
                    <span className="font-mono tabular-nums">
                      {Math.round(failBelow * 100)}–{Math.round(passAt * 100) - 1}%
                    </span>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span>Pass</span>
                    <span className="font-mono tabular-nums">
                      ≥ {Math.round(passAt * 100)}%
                    </span>
                  </div>
                </div>
              </div>

              <div
                id="sim-verdict"
                className="min-w-0 shrink-0 rounded-[14px] border border-border bg-card px-5 py-5"
              >
                <div className="mb-2.5 flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
                    Verdict
                  </div>
                  <Badge
                    variant={verdict?.variant ?? "muted"}
                    className="h-auto rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold"
                  >
                    {statusLabel}
                  </Badge>
                </div>
                <p className="text-[13px] leading-relaxed text-pretty break-words">
                  {sim.judge.reason || "No judge reason recorded."}
                </p>
                {sim.judge.suggestions.length > 0 && (
                  <ul className="mt-3 list-disc space-y-1.5 pl-4 text-[12.5px] leading-relaxed text-muted-foreground">
                    {sim.judge.suggestions.map((s) => (
                      <li key={s} className="break-words text-pretty">
                        {s}
                      </li>
                    ))}
                  </ul>
                )}
                {sim.rules.failures.length > 0 && (
                  <ul className="mt-3 list-disc space-y-1.5 pl-4 text-[12.5px] leading-relaxed text-fail">
                    {sim.rules.failures.map((f) => (
                      <li key={f} className="break-words text-pretty">
                        {f}
                      </li>
                    ))}
                  </ul>
                )}
                {toolSummary && (
                  <p className="mt-3 text-[12px] text-muted-foreground">{toolSummary}</p>
                )}
                {findings.items.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setView("improvements")}
                    className="mt-3.5 inline-flex items-center gap-1.5 text-[12.5px] font-medium text-primary underline-offset-2 hover:underline"
                  >
                    <Sparkles className="size-3.5" />
                    {findings.items.length} suggested{" "}
                    {findings.items.length === 1 ? "improvement" : "improvements"}
                  </button>
                )}
              </div>
            </aside>
          </div>
        </div>
      )}

      {audioSrc && (
        <CallAudioPlayer
          src={audioSrc}
          agentLabel={agentLabel}
          callerLabel={callerLabel}
          segments={segments}
          seekRequest={seekRequest}
          onTimeUpdate={onPlayerTime}
          onDuration={setAudioDuration}
          className="shrink-0"
        />
      )}
    </div>
  );
}
