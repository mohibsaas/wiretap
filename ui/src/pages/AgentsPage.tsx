import { useEffect, useMemo, useState } from "react";
import { Trash2, Plus } from "lucide-react";
import { ConnectAgentDialog } from "@/components/ConnectAgentDialog";
import { PageHeader } from "@/components/PageHeader";
import { TruncatedText } from "@/components/TruncatedText";
import { Button } from "@/components/ui/button";
import { client, type AgentRow } from "@/lib/api";
import { cn } from "@/lib/utils";

function providerLabel(platform?: string | null): string {
  if (!platform) return "—";
  const map: Record<string, string> = {
    retell: "Retell",
    vapi: "Vapi",
    elevenlabs: "ElevenLabs",
    livekit: "LiveKit",
    bland: "Bland",
    bolna: "Bolna",
    synthflow: "Synthflow",
  };
  const key = platform.toLowerCase();
  return map[key] || platform;
}

function agentDisplayName(a: AgentRow): string {
  return a.name || a.agent_id || a.id || a.suite || "Untitled agent";
}

function agentSubtitle(a: AgentRow): string {
  const parts: string[] = [];
  if (typeof a.scenario_count === "number") {
    parts.push(
      `${a.scenario_count} scenario${a.scenario_count === 1 ? "" : "s"}`,
    );
  }
  if (a.transport) parts.push(a.transport);
  return parts.join(" · ") || "Local agent";
}

function agentStatus(a: AgentRow): {
  label: string;
  tone: "pass" | "warn" | "muted";
} {
  if (a.connected || a.agent_id) {
    return { label: "Ready", tone: "pass" };
  }
  return { label: "Incomplete", tone: "warn" };
}

export function AgentsPage() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  function reload() {
    client
      .agents()
      .then(setAgents)
      .catch((e: Error) => setError(e.message));
  }

  useEffect(() => {
    reload();
  }, []);

  const meta = useMemo(() => {
    const n = agents.length;
    return `${n} agent${n === 1 ? "" : "s"}`;
  }, [agents.length]);

  async function removeAgent(a: AgentRow) {
    const suite = a.suite?.trim();
    if (!suite) {
      setError("This agent has no local suite to delete.");
      return;
    }
    const label = agentDisplayName(a);
    if (
      !window.confirm(
        `Delete “${label}” and its suite (${suite})? This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeleting(suite);
    setError(null);
    try {
      await client.deleteSuite(suite);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Agents"
        meta={meta}
        subtitle="The voice agents whose lines you tap."
        action={
          <Button className="rounded-full" onClick={() => setConnectOpen(true)}>
            <Plus data-icon="inline-start" />
            Add agent
          </Button>
        }
      />

      {error && <p className="text-sm text-fail">{error}</p>}

      <div className="overflow-x-auto rounded-[14px] border border-border bg-card">
        <div className="min-w-[560px]">
          <div
            className="grid gap-0 border-b border-border bg-[var(--wt-section)] px-5 py-2.5 text-[10.5px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase"
            style={{
              gridTemplateColumns: "minmax(200px,1.6fr) 140px 120px 56px",
            }}
          >
            <div>Agent</div>
            <div>Provider</div>
            <div>Status</div>
            <div className="text-right"> </div>
          </div>

          {agents.length === 0 && !error ? (
            <div className="px-5 py-10 text-sm text-muted-foreground text-pretty">
              No agents yet.{" "}
              <button
                type="button"
                className="font-medium text-foreground underline-offset-2 hover:underline"
                onClick={() => setConnectOpen(true)}
              >
                Add agent
              </button>{" "}
              or import from the CLI, then generate a suite.
            </div>
          ) : (
            agents.map((a, i) => {
              const status = agentStatus(a);
              const name = agentDisplayName(a);
              const canDelete = Boolean(a.suite);
              return (
                <div
                  key={`${a.id}-${a.suite}-${i}`}
                  className="grid items-center gap-0 border-b border-border px-5 py-3.5 last:border-b-0 transition-colors hover:bg-[var(--wt-section)]"
                  style={{
                    gridTemplateColumns: "minmax(200px,1.6fr) 140px 120px 56px",
                  }}
                >
                  <div className="min-w-0 pr-3">
                    <TruncatedText
                      text={name}
                      className="text-[13.5px] font-semibold leading-snug text-foreground"
                    />
                    <TruncatedText
                      text={agentSubtitle(a)}
                      className="mt-0.5 text-xs leading-snug text-[var(--wt-text-muted)]"
                    />
                  </div>

                  <div className="min-w-0 pr-3 text-[13px] text-muted-foreground">
                    <TruncatedText text={providerLabel(a.platform)} />
                  </div>

                  <div className="pr-3">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12px] font-semibold",
                        status.tone === "pass" &&
                          "border-[var(--wt-green-600)] bg-[var(--wt-green-100)] text-[var(--wt-green-700)]",
                        status.tone === "warn" &&
                          "border-border bg-[var(--wt-section)] text-foreground",
                        status.tone === "muted" &&
                          "border-border bg-muted text-muted-foreground",
                      )}
                    >
                      <span
                        className={cn(
                          "size-[7px] rounded-full",
                          status.tone === "pass" && "bg-pass",
                          status.tone === "warn" && "bg-warn",
                          status.tone === "muted" && "bg-muted-foreground",
                        )}
                      />
                      {status.label}
                    </span>
                  </div>

                  <div className="flex justify-end">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      disabled={!canDelete || deleting === a.suite}
                      aria-label={`Delete ${name}`}
                      onClick={() => void removeAgent(a)}
                    >
                      <Trash2 className="size-4 text-muted-foreground" />
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      <ConnectAgentDialog
        open={connectOpen}
        onOpenChange={setConnectOpen}
        onConnected={reload}
      />
    </div>
  );
}
