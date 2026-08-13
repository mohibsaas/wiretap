import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client, type Simulation, type ToolCall } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function ToolRow({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const args = Object.entries(call.arguments ?? {});
  const variant =
    call.status === "ok" ? "pass" : call.status === "error" ? "fail" : "warn";
  return (
    <div className="border-l-2 border-border pl-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          tool
        </span>
        <code className="font-mono text-xs">{call.name}</code>
        <Badge variant={variant}>{call.status}</Badge>
        {call.at_seconds !== null && (
          <span className="text-[11px] text-muted-foreground">
            {call.at_seconds.toFixed(1)}s
          </span>
        )}
        {args.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
          >
            {open ? "hide arguments" : "arguments"}
          </button>
        )}
      </div>
      {open && args.length > 0 && (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground">
          {args.map(([k, v]) => (
            <div key={k} className="contents">
              <dt>{k}</dt>
              <dd className="break-all">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {call.result_summary && (
        <p className="mt-1 font-mono text-[11px] text-muted-foreground break-all">
          {call.result_summary}
        </p>
      )}
    </div>
  );
}

export function SimulationDetailPage() {
  const { simulationId = "", batchId = "" } = useParams();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTurn, setActiveTurn] = useState<number | null>(null);

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

  // turn_index counts the turns that preceded a call, so it renders *before*
  // that turn. It is best-effort — anything unplaceable is grouped at the end
  // rather than guessed into the wrong slot.
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
    const parts = [`${sim.tool_calls.length} called`];
    if (missing.length > 0) parts.push(`${missing.join(", ")} never called`);
    return `Tools: ${parts.join(" · ")}`;
  }, [sim]);

  const audioSrc = sim?.audio_path
    ? `/api/simulations/${simulationId}/audio`
    : null;

  const backTo = batchId
    ? `/evaluations/${batchId}`
    : sim?.batch_id
      ? `/evaluations/${sim.batch_id}`
      : "/evaluations";

  if (!sim && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className={`space-y-6 ${audioSrc ? "pb-28" : ""}`}>
      <div>
        <Link
          to={backTo}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← {batchId || sim?.batch_id ? "Evaluation run" : "Evaluations"}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h1>
        {sim && (
          <p className="mt-1 text-sm text-muted-foreground">
            {sim.suite_id}
            {sim.persona_name ? ` · ${sim.persona_name}` : ""}
            {sim.meta?.platform ? ` · ${String(sim.meta.platform)}` : ""}
            {sim.meta?.agent_id ? ` · ${String(sim.meta.agent_id)}` : ""}
          </p>
        )}
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      {sim && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={sim.meta?.inconclusive ? "warn" : sim.passed ? "pass" : "fail"}
            >
              {sim.meta?.inconclusive ? "inconclusive" : sim.passed ? "pass" : "fail"}
            </Badge>
            <span className="text-xs text-muted-foreground">{sim.created_at}</span>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Judge</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p>{sim.judge.reason}</p>
              {!sim.passed && sim.judge.suggestions.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  {sim.judge.suggestions.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              )}
              {sim.rules.failures.length > 0 && (
                <div className="text-fail">
                  Rules: {sim.rules.failures.join("; ")}
                </div>
              )}
              {toolSummary && (
                <div className="text-xs text-muted-foreground">{toolSummary}</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Transcript</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {sim.transcript.length === 0 && (
                <p className="text-sm text-muted-foreground">Empty transcript.</p>
              )}
              {sim.transcript.map((t, i) => (
                <div key={`turn-${i}`} className="space-y-3">
                  {(tools.byTurn.get(i) ?? []).map((call, n) => (
                    <ToolRow key={`${call.name}-${i}-${n}`} call={call} />
                  ))}
                  <div
                    className={`text-sm transition-colors ${
                      activeTurn === i ? "ring-1 ring-accent rounded-md" : ""
                    }`}
                  >
                    <div className="mb-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {t.role === "user" ? "caller" : "agent"}
                    </div>
                    <div className="rounded-md bg-muted/60 px-3 py-2">{t.text}</div>
                  </div>
                </div>
              ))}
              {(tools.byTurn.get(tools.total) ?? []).map((call, n) => (
                <ToolRow key={`tail-${call.name}-${n}`} call={call} />
              ))}
              {tools.unplaced.length > 0 && (
                <div className="space-y-3 pt-1">
                  <p className="text-xs text-muted-foreground">
                    Tool calls with no known position in the transcript:
                  </p>
                  {tools.unplaced.map((call, n) => (
                    <ToolRow key={`unplaced-${call.name}-${n}`} call={call} />
                  ))}
                </div>
              )}
              {sim.meta?.tool_capture !== "ok" && (
                <p className="pt-1 text-xs text-muted-foreground">
                  Tool calls not observable for this agent.
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {audioSrc && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 backdrop-blur">
          <div className="mx-auto flex max-w-3xl flex-col gap-2 px-4 py-3">
            <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span>Call audio</span>
              <button
                type="button"
                className="underline-offset-2 hover:underline"
                onClick={() => setActiveTurn(null)}
              >
                clear highlight
              </button>
            </div>
            <audio
              controls
              className="w-full"
              src={audioSrc}
              onPlay={() => {
                if (sim && sim.transcript.length > 0) setActiveTurn(0);
              }}
            >
              <track kind="captions" />
            </audio>
            <p className="text-[11px] text-muted-foreground">
              Transcript is above. Playback is the recorded call mix when the
              transport captured audio (Vapi / Retell). Text dry-runs have no audio.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
