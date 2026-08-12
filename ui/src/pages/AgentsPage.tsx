import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { client, type AgentRow } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AgentsPage() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .agents()
      .then(setAgents)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Live agents from local suites. Add more with{" "}
            <code className="font-mono text-xs">wiretap import</code>.
          </p>
        </div>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      <Card>
        <CardHeader>
          <CardTitle>Connected</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border p-0">
          {agents.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">
              No agents yet. First-time setup runs automatically; after that use{" "}
              <code className="font-mono text-xs">wiretap import retell|vapi</code>.
            </p>
          )}
          {agents.map((a, i) => (
            <div
              key={`${a.id}-${a.suite}-${i}`}
              className="flex items-center justify-between gap-4 px-4 py-3"
            >
              <div>
                <div className="font-medium">
                  {a.name || a.id || a.suite || "agent"}
                </div>
                <div className="text-xs text-muted-foreground">
                  {[a.platform, a.id, a.suite].filter(Boolean).join(" · ")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {a.platform && <Badge variant="muted">{a.platform}</Badge>}
                {a.suite && (
                  <Link
                    to={`/suites/${a.suite}`}
                    className="text-sm text-accent underline-offset-2 hover:underline"
                  >
                    suite
                  </Link>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
