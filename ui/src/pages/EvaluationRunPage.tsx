import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client, type EvaluationRun } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function EvaluationRunPage() {
  const { batchId = "" } = useParams();
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .evaluation(batchId)
      .then(setRun)
      .catch((e: Error) => setError(e.message));
  }, [batchId]);

  if (!run && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const sims = run?.simulations || [];

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/evaluations"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← Evaluations
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          {run?.suite_id || "Evaluation"}
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{batchId}</p>
        {run?.created_at && (
          <p className="mt-1 text-sm text-muted-foreground">{run.created_at}</p>
        )}
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      {run && (
        <>
          <div className="flex flex-wrap gap-2 text-sm">
            <Badge variant="pass">{run.passed} passed</Badge>
            <Badge variant="fail">{run.failed} failed</Badge>
            {(run.inconclusive || 0) > 0 && (
              <Badge variant="warn">{run.inconclusive} inconclusive</Badge>
            )}
            <Badge variant="muted">{run.total} total</Badge>
            {run.status && <Badge variant="muted">{run.status}</Badge>}
          </div>
          {run.error && <p className="text-sm text-fail">{run.error}</p>}

          <Card>
            <CardHeader>
              <CardTitle>Scenarios</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border p-0">
              {sims.length === 0 && (
                <p className="p-4 text-sm text-muted-foreground">
                  No scenario results saved for this run.
                </p>
              )}
              {sims.map((s) => (
                <Link
                  key={s.simulation_id}
                  to={`/evaluations/${batchId}/scenarios/${s.simulation_id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-muted/40"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {s.scenario_name || s.scenario_id}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {s.persona_name || s.persona_id}
                      {s.audio_path ? " · audio" : ""}
                    </div>
                  </div>
                  <Badge
                    variant={
                      s.meta?.inconclusive ? "warn" : s.passed ? "pass" : "fail"
                    }
                  >
                    {s.meta?.inconclusive
                      ? "inconclusive"
                      : s.passed
                        ? "pass"
                        : "fail"}
                  </Badge>
                </Link>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
