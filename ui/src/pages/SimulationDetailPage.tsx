import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client, type Simulation } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SimulationDetailPage() {
  const { simulationId = "" } = useParams();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .simulation(simulationId)
      .then(setSim)
      .catch((e: Error) => setError(e.message));
  }, [simulationId]);

  if (!sim && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/evaluations"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← Evaluations
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Simulation</h1>
        {sim && (
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            {sim.suite_id}/{sim.scenario_id}
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
                <div key={`${t.role}-${i}`} className="text-sm">
                  <div className="mb-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {t.role === "user" ? "caller" : "agent"}
                  </div>
                  <div className="rounded-md bg-muted/60 px-3 py-2">{t.text}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
