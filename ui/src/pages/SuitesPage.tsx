import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { client, type SuiteSummary } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SuitesPage() {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .suites()
      .then(setSuites)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Test suites</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Local suites under .wiretap/suites/
        </p>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      <div className="grid gap-3">
        {suites.length === 0 && !error && (
          <Card>
            <CardContent className="py-8 text-sm text-muted-foreground">
              No suites yet. Use <code className="font-mono">wiretap import</code> or{" "}
              <code className="font-mono">wiretap import</code>.
            </CardContent>
          </Card>
        )}
        {suites.map((s) => (
          <Link key={s.name} to={`/suites/${s.name}`} className="block">
            <Card className="transition-colors hover:bg-muted/40">
              <CardHeader className="flex flex-row items-center justify-between gap-4">
                <CardTitle className="font-mono text-base">{s.name}</CardTitle>
                <div className="flex gap-2">
                  {s.platform && <Badge variant="muted">{s.platform}</Badge>}
                  {s.transport && <Badge>{s.transport}</Badge>}
                </div>
              </CardHeader>
              <CardContent className="pt-0 text-sm text-muted-foreground">
                {s.error ? (
                  <span className="text-fail">{s.error}</span>
                ) : (
                  <>
                    {s.scenario_count ?? 0} scenarios · {s.persona_count ?? 0} personas
                  </>
                )}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
