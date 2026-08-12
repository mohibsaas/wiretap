import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client, type Batch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type LiveEvent = {
  type: string;
  scenario_id?: string;
  simulation_id?: string;
  passed?: boolean;
  inconclusive?: boolean;
  reason?: string;
  error?: string;
};

export function BatchPage() {
  const { batchId = "" } = useParams();
  const [batch, setBatch] = useState<Batch | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .batch(batchId)
      .then(setBatch)
      .catch((e: Error) => setError(e.message));

    const es = new EventSource(`/api/batches/${batchId}/events`);
    es.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data) as LiveEvent;
        setEvents((prev) => [...prev, ev]);
        if (ev.type === "batch_completed" || ev.type === "batch_failed") {
          client.batch(batchId).then(setBatch);
        }
      } catch {
        /* ignore */
      }
    };
    es.addEventListener("end", () => {
      es.close();
      client.batch(batchId).then(setBatch).catch(() => undefined);
    });
    es.onerror = () => {
      es.close();
    };
    return () => es.close();
  }, [batchId]);

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-xs text-muted-foreground hover:text-foreground">
          ← Suites
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Live batch</h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{batchId}</p>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      {batch && (
        <div className="flex items-center gap-2 text-sm">
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
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Progress</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 font-mono text-xs">
          {events.length === 0 && (
            <p className="font-sans text-sm text-muted-foreground">Waiting for events…</p>
          )}
          {events.map((ev, i) => (
            <div key={`${ev.type}-${i}`} className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">{ev.type}</span>
              {ev.scenario_id && <span>{ev.scenario_id}</span>}
              {typeof ev.passed === "boolean" && (
                <Badge variant={ev.inconclusive ? "warn" : ev.passed ? "pass" : "fail"}>
                  {ev.inconclusive ? "inconclusive" : ev.passed ? "pass" : "fail"}
                </Badge>
              )}
              {ev.simulation_id && (
                <Link
                  className="text-accent underline-offset-2 hover:underline"
                  to={`/evaluations/${ev.simulation_id}`}
                >
                  open
                </Link>
              )}
              {ev.reason && (
                <span className="w-full truncate text-muted-foreground">{ev.reason}</span>
              )}
              {ev.error && <span className="text-fail">{ev.error}</span>}
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
            {batch.results.map((r) => (
              <Link
                key={r.simulation_id}
                to={`/evaluations/${r.simulation_id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-muted/40"
              >
                <span className="font-mono text-sm">{r.scenario_id}</span>
                <Badge
                  variant={r.meta?.inconclusive ? "warn" : r.passed ? "pass" : "fail"}
                >
                  {r.meta?.inconclusive ? "inconclusive" : r.passed ? "pass" : "fail"}
                </Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
