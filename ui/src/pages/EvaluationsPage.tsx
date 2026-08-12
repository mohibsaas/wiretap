import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { client, type EvaluationRun } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export function EvaluationsPage() {
  const [items, setItems] = useState<EvaluationRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      client
        .evaluations()
        .then(setItems)
        .catch((e: Error) => setError(e.message));
    void load();
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const totalScenarios = items.reduce((n, r) => n + (r.total || 0), 0);
  const passed = items.reduce((n, r) => n + (r.passed || 0), 0);
  const failed = items.reduce((n, r) => n + (r.failed || 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Evaluations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Each row is one suite run. Open it to see individual scenario results.
        </p>
      </div>
      <div className="flex gap-3 text-sm">
        <Badge variant="muted">{items.length} runs</Badge>
        <Badge variant="pass">{passed} passed</Badge>
        <Badge variant="fail">{failed} failed</Badge>
        <Badge variant="muted">{totalScenarios} scenarios</Badge>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      <Card className="overflow-hidden">
        <CardContent className="divide-y divide-border p-0">
          {items.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">
              No evaluations yet. Open a suite and start simulations.
            </p>
          )}
          {items.map((r) => {
            const ok = (r.failed || 0) === 0 && (r.total || 0) > 0;
            const partial = (r.passed || 0) > 0 && (r.failed || 0) > 0;
            return (
              <Link
                key={r.batch_id}
                to={`/evaluations/${r.batch_id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-muted/40"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">
                    {r.suite_id || "suite"}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {r.total || 0} scenarios
                    {r.created_at ? ` · ${r.created_at}` : ""}
                    {r.status ? ` · ${r.status}` : ""}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {r.passed}/{r.total}
                  </span>
                  <Badge variant={ok ? "pass" : partial ? "warn" : "fail"}>
                    {ok ? "pass" : partial ? "mixed" : "fail"}
                  </Badge>
                </div>
              </Link>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
