import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { client, type AgentRow } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
            Live agents discovered from local suites. Each suite embeds one default
            agent; you can run any suite against another agent at simulate time.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to="/onboard?again=1">Add agent</Link>
        </Button>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}
      <Card>
        <CardHeader>
          <CardTitle>Connected</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border p-0">
          {agents.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">
              No agents yet. Use <strong>Add agent</strong> (onboarding) or{" "}
              <code className="font-mono text-xs">wiretap import retell|vapi</code>,
              then generate tests with onboarding or{" "}
              <code className="font-mono text-xs">wiretap suite generate</code>.
            </p>
          )}
          {agents.map((a, i) => (
            <div
              key={`${a.id}-${a.suite}-${i}`}
              className="flex items-center justify-between gap-4 px-4 py-3"
            >
              <div>
                <div className="font-medium">
                  {a.name || a.agent_id || a.id || a.suite || "agent"}
                </div>
                <div className="text-xs text-muted-foreground">
                  {[a.platform, a.agent_id || a.id, a.suite]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {a.platform && <Badge variant="muted">{a.platform}</Badge>}
                {a.suite && (
                  <Link
                    to={`/suites/${a.suite}`}
                    className="text-sm text-accent underline-offset-2 hover:underline"
                  >
                    suite / generate
                  </Link>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>How to add more</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            <strong className="text-foreground">UI:</strong> Add agent → connect
            platform + agent id → generate category tests. Open a suite and use{" "}
            <em>Run against agent</em> to point tests at a different agent.
          </p>
          <p>
            <strong className="text-foreground">CLI:</strong>{" "}
            <code className="font-mono text-xs">wiretap import retell --agent-id …</code>{" "}
            then{" "}
            <code className="font-mono text-xs">
              wiretap suite generate -s SUITE -C emotional,compliance -n 5
            </code>
            . Reuse tests:{" "}
            <code className="font-mono text-xs">
              wiretap simulate -s SUITE --all --agent-from OTHER_SUITE
            </code>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
