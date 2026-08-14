import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  client,
  type AgentNumberTarget,
  type AgentRow,
  type PstnStatus,
  type SuiteSummary,
} from "@/lib/api";
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
import { AppSelect } from "@/components/AppSelect";

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
  const [concurrency, setConcurrency] = useState(() => {
    try {
      const raw = localStorage.getItem("wiretap.defaultConcurrency");
      const n = raw ? Number(raw) : 4;
      if (Number.isFinite(n) && n >= 1 && n <= 32) return Math.floor(n);
    } catch {
      /* ignore */
    }
    return 4;
  });
  const [strict, setStrict] = useState(false);
  const [transport, setTransport] = useState<"web" | "phone">("web");
  const [phone, setPhone] = useState("");
  const [pstn, setPstn] = useState<PstnStatus | null>(null);
  const [target, setTarget] = useState<AgentNumberTarget | null>(null);
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
    void client.pstnStatus().then(setPstn).catch(() => setPstn(null));
    setAgentFrom("");
    setConcurrency(() => {
      try {
        const raw = localStorage.getItem("wiretap.defaultConcurrency");
        const n = raw ? Number(raw) : 4;
        if (Number.isFinite(n) && n >= 1 && n <= 32) return Math.floor(n);
      } catch {
        /* ignore */
      }
      return 4;
    });
    setStrict(false);
    setTransport("web");
    setPhone("");
  }, [open, initialSuite]);

  // Show the number a phone run would dial rather than failing at dial time.
  useEffect(() => {
    if (!open || !suite) {
      setTarget(null);
      return;
    }
    let live = true;
    void client
      .pstnAgentNumber(suite, agentFrom || null)
      .then((found) => {
        if (!live) return;
        setTarget(found);
        setPhone(found.number || "");
      })
      .catch(() => {
        if (live) setTarget(null);
      });
    return () => {
      live = false;
    };
  }, [open, suite, agentFrom]);

  const otherAgents = useMemo(
    () => agents.filter((a) => a.suite && a.suite !== suite),
    [agents, suite],
  );

  const selected = suites.find((s) => s.name === suite);
  const byPhone = transport === "phone";
  const phoneReady = pstn?.ready === true;

  async function start() {
    if (!suite) return;
    setBusy(true);
    setError(null);
    try {
      const { batch_id } = await client.startBatch({
        suite,
        all: true,
        // One softphone registration, so phone runs are serial regardless.
        concurrency: byPhone ? 1 : Math.max(1, concurrency),
        strict,
        agent_from: agentFrom || null,
        transport: byPhone ? "phone" : null,
        phone: byPhone ? phone.trim() || null : null,
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
      <DialogContent className="gap-0 overflow-hidden rounded-[18px] border-border p-0 shadow-[0_30px_80px_-20px_rgba(41,41,39,0.28)] sm:max-w-[480px]">
        <div className="flex min-w-0 flex-col gap-4 p-6 pb-4">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold tracking-[-0.01em]">
              New run
            </DialogTitle>
            <DialogDescription className="text-[13px] leading-relaxed">
              Tap the line on an agent and put a suite on the record.
            </DialogDescription>
          </DialogHeader>

          <div className="flex min-w-0 flex-col gap-3.5">
            <div className="flex min-w-0 flex-col gap-1.5">
              <Label htmlFor="run-suite">Suite</Label>
              <AppSelect
                id="run-suite"
                mono
                value={suite || "__none__"}
                onValueChange={(v) => setSuite(v === "__none__" ? "" : v)}
                placeholder="Select a suite"
                options={
                  suites.length === 0
                    ? [
                        {
                          value: "__none__",
                          label: "No suites yet",
                          disabled: true,
                        },
                      ]
                    : suites.map((s) => ({
                        value: s.name,
                        label:
                          s.name +
                          (s.scenario_count != null
                            ? ` · ${s.scenario_count} scenarios`
                            : ""),
                      }))
                }
              />
              {selected?.platform && (
                <p className="text-xs text-muted-foreground">
                  {selected.platform}
                  {selected.transport ? ` · ${selected.transport}` : ""}
                </p>
              )}
            </div>

            <div className="flex min-w-0 flex-col gap-1.5">
              <Label htmlFor="run-agent">Target agent</Label>
              <AppSelect
                id="run-agent"
                mono
                value={agentFrom || "__default__"}
                onValueChange={(v) =>
                  setAgentFrom(v === "__default__" ? "" : v)
                }
                options={[
                  { value: "__default__", label: "Suite default" },
                  ...otherAgents
                    .filter((a) => Boolean(a.suite))
                    .map((a) => ({
                      value: a.suite as string,
                      label:
                        (a.name || a.agent_id || a.suite || "agent") +
                        (a.platform ? ` · ${a.platform}` : ""),
                    })),
                ]}
              />
            </div>

            <div className="flex min-w-0 flex-col gap-1.5">
              <Label htmlFor="run-transport">Reach agent via</Label>
              <AppSelect
                id="run-transport"
                value={transport}
                onValueChange={(v) =>
                  setTransport(v === "phone" ? "phone" : "web")
                }
                options={[
                  {
                    value: "web",
                    label: `Web${selected?.transport ? ` · ${selected.transport}` : ""}`,
                  },
                  {
                    value: "phone",
                    label: `Phone · real call${phoneReady ? "" : " (not set up)"}`,
                    disabled: !phoneReady,
                  },
                ]}
              />
              {!phoneReady && (
                <p className="text-xs text-muted-foreground">
                  Phone runs need Twilio —{" "}
                  <Link to="/settings" className="underline">
                    finish phone testing in Settings
                  </Link>
                  {pstn?.missing?.length ? ` (${pstn.missing.join(", ")})` : ""}
                  .
                </p>
              )}
            </div>

            {byPhone && (
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="run-phone">Agent number to dial</Label>
                <Input
                  id="run-phone"
                  className="h-10 rounded-[10px] font-mono text-sm"
                  placeholder="+15551234567"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {target?.number && target.source !== "request"
                    ? `From the ${target.source === "suite" ? "suite" : "last run"}.`
                    : "No number saved for this agent yet — enter the one that reaches it."}
                  {pstn?.from_number
                    ? ` Calling from ${pstn.from_number}.`
                    : ""}
                </p>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="run-concurrency">Concurrency</Label>
                <Input
                  id="run-concurrency"
                  type="number"
                  min={1}
                  max={32}
                  className="h-10 w-20 rounded-[10px]"
                  value={byPhone ? 1 : concurrency}
                  disabled={byPhone}
                  onChange={(e) =>
                    setConcurrency(Number(e.target.value) || 1)
                  }
                />
                {byPhone && (
                  <p className="text-xs text-muted-foreground">
                    One call at a time.
                  </p>
                )}
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
        </div>

        <DialogFooter className="gap-2 rounded-b-[18px] sm:justify-end">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            onClick={start}
            disabled={busy || !suite || (byPhone && !phone.trim())}
          >
            {busy ? "Starting…" : "Start run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
