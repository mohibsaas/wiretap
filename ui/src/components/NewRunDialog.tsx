import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { client, type AgentRow, type SuiteSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-select a suite when opening from a plan row. */
  initialSuite?: string | null;
};

export function NewRunDialog({ open, onOpenChange, initialSuite }: Props) {
  const navigate = useNavigate();
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [suite, setSuite] = useState("");
  const [agentFrom, setAgentFrom] = useState("");
  const [concurrency, setConcurrency] = useState(4);
  const [strict, setStrict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    void client.suites().then((rows) => {
      setSuites(rows.filter((s) => !s.error));
      const pick = initialSuite || rows.find((s) => !s.error)?.name || "";
      setSuite(pick);
    });
    void client.agents().then(setAgents).catch(() => setAgents([]));
    setAgentFrom("");
    setConcurrency(4);
    setStrict(false);
  }, [open, initialSuite]);

  const otherAgents = useMemo(
    () => agents.filter((a) => a.suite && a.suite !== suite),
    [agents, suite],
  );

  const selected = suites.find((s) => s.name === suite);

  async function start() {
    if (!suite) return;
    setBusy(true);
    setError(null);
    try {
      const { batch_id } = await client.startBatch({
        suite,
        all: true,
        concurrency: Math.max(1, concurrency),
        strict,
        agent_from: agentFrom || null,
      });
      onOpenChange(false);
      navigate(`/batches/${batch_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[460px] rounded-[18px] border-border p-6 shadow-[0_30px_80px_-20px_rgba(41,41,39,0.28)]">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold tracking-[-0.01em]">
            New run
          </DialogTitle>
          <DialogDescription className="text-[13px] leading-relaxed">
            Tap the line on an agent and put a suite on the record.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3.5 py-1">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="run-suite">Suite</Label>
            <select
              id="run-suite"
              className="h-10 w-full rounded-[10px] border border-input bg-card px-3 font-mono text-[13px]"
              value={suite}
              onChange={(e) => setSuite(e.target.value)}
            >
              {suites.length === 0 && <option value="">No suites yet</option>}
              {suites.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                  {s.scenario_count != null ? ` · ${s.scenario_count} scenarios` : ""}
                </option>
              ))}
            </select>
            {selected?.platform && (
              <p className="text-xs text-muted-foreground">
                {selected.platform}
                {selected.transport ? ` · ${selected.transport}` : ""}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="run-agent">Target agent</Label>
            <select
              id="run-agent"
              className="h-10 w-full rounded-[10px] border border-input bg-card px-3 font-mono text-[13px]"
              value={agentFrom}
              onChange={(e) => setAgentFrom(e.target.value)}
            >
              <option value="">Suite default</option>
              {otherAgents.map((a) => (
                <option key={`${a.suite}-${a.agent_id}`} value={a.suite || ""}>
                  {(a.name || a.agent_id || a.suite) +
                    (a.platform ? ` · ${a.platform}` : "")}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="run-concurrency">Concurrency</Label>
              <Input
                id="run-concurrency"
                type="number"
                min={1}
                max={32}
                className="h-10 w-20 rounded-[10px]"
                value={concurrency}
                onChange={(e) => setConcurrency(Number(e.target.value) || 1)}
              />
            </div>
            <label className="mt-5 flex items-center gap-2 text-sm">
              <Checkbox
                checked={strict}
                onCheckedChange={(v) => setStrict(v === true)}
              />
              Strict caller
            </label>
          </div>

          {error && <p className="text-sm text-fail">{error}</p>}
        </div>

        <DialogFooter className="gap-2 sm:justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={start} disabled={busy || !suite}>
            {busy ? "Starting…" : "Start run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
