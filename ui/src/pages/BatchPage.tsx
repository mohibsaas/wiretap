import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client, type Batch } from "@/lib/api";
import { simulationVerdict } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type LiveEvent = {
  type: string;
  scenario_id?: string;
  scenario_name?: string;
  simulation_id?: string;
  passed?: boolean;
  inconclusive?: boolean;
  reason?: string;
  error?: string;
  scenario_count?: number;
  concurrency?: number;
  failures?: number;
};

export function BatchPage() {
  const { batchId = "" } = useParams();
  const [batch, setBatch] = useState<Batch | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    return client
      .batch(batchId)
      .then(setBatch)
      .catch((e: Error) => setError(e.message));
  }, [batchId]);

  useEffect(() => {
    void refresh();

    // Poll as a reliable fallback — EventSource can miss/end silently.
    const poll = window.setInterval(() => {
      void refresh();
    }, 1000);

    const es = new EventSource(`/api/batches/${batchId}/events`);
    es.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data) as LiveEvent;
        setEvents((prev) => [...prev, ev]);
        if (
          ev.type === "batch_completed" ||
          ev.type === "batch_failed" ||
          ev.type === "simulation_finished" ||
          ev.type === "simulation_failed"
        ) {
          void refresh();
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    es.addEventListener("end", () => {
      es.close();
      void refresh();
    });
    es.onerror = () => {
      // Browser fires error when the stream closes; refresh final state.
      if (es.readyState === EventSource.CLOSED) {
        void refresh();
      }
    };

    return () => {
      window.clearInterval(poll);
      es.close();
    };
  }, [batchId, refresh]);

  const done = batch?.status === "completed" || batch?.status === "failed";

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/evaluations"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← Simulations
        </Link>
        <h1 className="mt-2 text-[22px] font-semibold tracking-[-0.005em]">Live run</h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{batchId}</p>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      {batch && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge
            variant={
              batch.status === "completed"
                ? "pass"
                : batch.status === "failed"
                  ? "fail"
                  : "warn"
            }
          >
            {batch.status}
          </Badge>
          <span className="text-muted-foreground">suite {batch.suite}</span>
          {done && (
            <Link
              to={`/evaluations?run=${encodeURIComponent(batchId)}`}
              className="text-primary underline-offset-2 hover:underline"
            >
              View tests →
            </Link>
          )}
        </div>
      )}
      {batch?.error && <p className="text-sm text-fail">{batch.error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Progress</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 font-mono text-xs">
          {events.length === 0 && !done && (
            <p className="font-sans text-sm text-muted-foreground">
              Running… results appear as each scenario finishes.
            </p>
          )}
          {events.map((ev, i) => (
            <div key={`${ev.type}-${i}`} className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">{ev.type}</span>
              {(ev.scenario_name || ev.scenario_id) && (
                <span>{ev.scenario_name || ev.scenario_id}</span>
              )}
              {typeof ev.concurrency === "number" && (
                <span className="text-muted-foreground">
                  concurrency {ev.concurrency}
                  {typeof ev.scenario_count === "number"
                    ? ` · ${ev.scenario_count} scenarios`
                    : ""}
                </span>
              )}
              {typeof ev.passed === "boolean" && (
                <Badge variant={ev.inconclusive ? "warn" : ev.passed ? "pass" : "fail"}>
                  {ev.inconclusive ? "inconclusive" : ev.passed ? "pass" : "fail"}
                </Badge>
              )}
              {ev.simulation_id && (
                <Link
                  className="text-accent underline-offset-2 hover:underline"
                  to={`/evaluations/${batchId}/scenarios/${ev.simulation_id}`}
                >
                  open
                </Link>
              )}
              {ev.reason && (
                <span className="w-full truncate text-muted-foreground">{ev.reason}</span>
              )}
              {ev.error && <span className="w-full text-fail">{ev.error}</span>}
            </div>
          ))}
        </CardContent>
      </Card>

      {batch && batch.results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Simulations</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border p-0">
            {batch.results.map((r) => {
              const v = simulationVerdict(r);
              return (
              <Link
                key={r.simulation_id || r.scenario_id}
                to={`/evaluations/${batchId}/scenarios/${r.simulation_id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-muted/40"
              >
                <span className="text-sm font-medium">
                  {r.scenario_name || r.scenario_id}
                </span>
                <Badge variant={v.variant}>
                  {v.label.toLowerCase()}
                  {v.pct != null ? ` · ${v.pct}%` : ""}
                </Badge>
              </Link>
              );
            })}
          </CardContent>
        </Card>
      )}

      {done && batch && batch.results.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Batch finished with no saved simulations. Check the progress log or API keys,
          then open{" "}
          <Link to="/evaluations" className="text-accent underline-offset-2 hover:underline">
            Evaluations
          </Link>
          .
        </p>
      )}
    </div>
  );
}
