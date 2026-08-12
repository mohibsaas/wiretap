import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { client, type Simulation } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export function SimulationsPage() {
  const [items, setItems] = useState<Simulation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .simulations()
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Simulations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Recent results from .wiretap/simulations/
        </p>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      <Card className="overflow-hidden">
        <CardContent className="divide-y divide-border p-0">
          {items.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No simulations yet.</p>
          )}
          {items.map((s) => (
            <Link
              key={s.simulation_id}
              to={`/simulations/${s.simulation_id}`}
              className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-muted/40"
            >
              <div className="min-w-0">
                <div className="font-mono text-sm">
                  {s.suite_id}/{s.scenario_id}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {s.created_at || s.simulation_id}
                </div>
              </div>
              <Badge
                variant={s.meta?.inconclusive ? "warn" : s.passed ? "pass" : "fail"}
              >
                {s.meta?.inconclusive ? "inconclusive" : s.passed ? "pass" : "fail"}
              </Badge>
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
