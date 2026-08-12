import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { client, type AgentRow, type SuiteDetail } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SuiteDetailPage() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const [suite, setSuite] = useState<SuiteDetail | null>(null);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [scenario, setScenario] = useState<string>("");
  const [all, setAll] = useState(true);
  const [strict, setStrict] = useState(false);
  const [concurrency, setConcurrency] = useState(1);
  const [agentFrom, setAgentFrom] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .suite(name)
      .then((s) => {
        setSuite(s);
        if (s.scenarios.length === 1) {
          setAll(false);
          setScenario(s.scenarios[0].id);
        }
      })
      .catch((e: Error) => setError(e.message));
    client.agents().then(setAgents).catch(() => undefined);
  }, [name]);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const { batch_id } = await client.startBatch({
        suite: name,
        all: all || !scenario,
        scenario: all ? null : scenario || null,
        concurrency,
        strict,
        agent_from: agentFrom || null,
      });
      navigate(`/batches/${batch_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!suite && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const otherAgents = agents.filter((a) => a.suite && a.suite !== name);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/" className="text-xs text-muted-foreground hover:text-foreground">
            ← Suites
          </Link>
          <h1 className="mt-2 font-mono text-2xl font-semibold tracking-tight">{name}</h1>
          {suite && (
            <p className="mt-1 text-sm text-muted-foreground">
              {suite.agent.platform || "generic"} · {suite.agent.transport}
              {suite.agent.agent_id ? ` · ${suite.agent.agent_id}` : ""}
            </p>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-fail">{error}</p>}

      {suite && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Start batch</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={all}
                  onChange={(e) => setAll(e.target.checked)}
                />
                Simulate all scenarios
              </label>
              {!all && (
                <select
                  className="h-9 w-full rounded-md border border-border bg-card px-3 text-sm"
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                >
                  <option value="">Select scenario…</option>
                  {suite.scenarios.map((sc) => (
                    <option key={sc.id} value={sc.id}>
                      {sc.name}
                    </option>
                  ))}
                </select>
              )}
              <div className="space-y-2">
                <label className="text-sm font-medium">Run against agent</label>
                <select
                  className="h-9 w-full rounded-md border border-border bg-card px-3 text-sm"
                  value={agentFrom}
                  onChange={(e) => setAgentFrom(e.target.value)}
                >
                  <option value="">Suite default ({suite.agent.agent_id || "embedded"})</option>
                  {otherAgents.map((a) => (
                    <option key={`${a.suite}-${a.agent_id}`} value={a.suite || ""}>
                      {(a.name || a.agent_id || a.suite) +
                        (a.platform ? ` · ${a.platform}` : "") +
                        (a.suite ? ` (from suite ${a.suite})` : "")}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">
                  Suites embed one default agent. Pick another suite&apos;s agent to
                  reuse these tests without editing YAML.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <label className="flex items-center gap-2">
                  Concurrency
                  <input
                    type="number"
                    min={1}
                    className="h-9 w-16 rounded-md border border-border bg-card px-2"
                    value={concurrency}
                    onChange={(e) => setConcurrency(Number(e.target.value) || 1)}
                  />
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={strict}
                    onChange={(e) => setStrict(e.target.checked)}
                  />
                  Strict caller
                </label>
              </div>
              <Button onClick={start} disabled={busy || (!all && !scenario)}>
                {busy ? "Starting…" : "Start simulations"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Scenarios</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border p-0">
              {suite.scenarios.map((sc) => (
                <div key={sc.id} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{sc.name}</span>
                    {sc.category && <Badge variant="muted">{sc.category}</Badge>}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                    {sc.success_criteria}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
