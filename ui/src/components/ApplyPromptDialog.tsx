import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  client,
  type AdviceFinding,
  type PromptDiffHunk,
  type PromptPreview,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const fieldLabelClass =
  "text-[10.5px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase";

export function isPromptFinding(finding: AdviceFinding) {
  return finding.target === "agent_prompt" && Boolean(finding.suggested_text?.trim());
}

export function promptFindingIdsForScenario(
  findings: AdviceFinding[] | undefined,
  scenarioId: string,
): string[] {
  return (findings || [])
    .filter(
      (f) =>
        isPromptFinding(f) &&
        Boolean(f.id) &&
        (f.affected_scenarios || []).includes(scenarioId),
    )
    .map((f) => f.id);
}

function skipReasonLabel(reason?: string) {
  if (reason === "already_in_selection") return "Same wording as another selected finding";
  return "Already present in the live prompt";
}

function PromptDiff({ hunks }: { hunks: PromptDiffHunk[] }) {
  const lines = useMemo(() => {
    const out: { op: string; text: string }[] = [];
    for (const hunk of hunks) {
      const parts = hunk.text.split("\n");
      parts.forEach((line, i) => {
        if (i === parts.length - 1 && line === "") return;
        out.push({ op: hunk.op, text: line });
      });
    }
    return out;
  }, [hunks]);

  if (lines.length === 0) {
    return (
      <p className="mt-1 text-[12.5px] text-muted-foreground">No line changes.</p>
    );
  }

  return (
    <pre className="mt-1 max-h-72 overflow-auto rounded-[10px] border border-border font-mono text-[11.5px] leading-[1.55]">
      {lines.map((line, i) => {
        const insert = line.op === "insert";
        const remove = line.op === "delete";
        return (
          <div
            key={`${i}-${line.op}`}
            className={cn(
              "flex gap-2 px-3 py-0.5 whitespace-pre-wrap break-words",
              insert && "bg-[color-mix(in_srgb,var(--pass)_16%,white)] text-[var(--wt-green-800)]",
              remove && "bg-[var(--wt-danger-surface)] text-[var(--wt-danger)]",
              !insert && !remove && "bg-[var(--wt-section)] text-muted-foreground",
            )}
          >
            <span className="w-3 shrink-0 select-none">
              {insert ? "+" : remove ? "−" : " "}
            </span>
            <span>{line.text || " "}</span>
          </div>
        );
      })}
    </pre>
  );
}

export function usePromptApply(batchId: string) {
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openPreview = async (findingIds: string[]) => {
    setError(null);
    setBusy(true);
    try {
      setPreview(await client.previewPrompt(batchId, findingIds));
      return true;
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "Could not load the live prompt.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const confirmApply = async () => {
    if (!preview) return false;
    setBusy(true);
    setError(null);
    try {
      await client.applyPrompt(
        batchId,
        preview.applied_finding_ids,
        preview.current_hash,
      );
      setPreview(null);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the live prompt.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    if (busy) return;
    setPreview(null);
    setError(null);
  };

  return { preview, busy, error, openPreview, confirmApply, close, setError };
}

export function ApplyPromptDialog({
  open,
  onOpenChange,
  preview,
  busy,
  error,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: PromptPreview | null;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onOpenChange(false);
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Apply to live prompt</DialogTitle>
          <DialogDescription>
            {preview
              ? `This overwrites the system prompt on ${preview.platform} agent ${preview.agent_id}. Green is new, red is removed, gray is unchanged.`
              : "Review the live prompt change before writing it to the agent."}
          </DialogDescription>
        </DialogHeader>
        {preview ? (
          <div className="space-y-3">
            {(preview.skipped?.length ?? 0) > 0 && (
              <div>
                <div className={fieldLabelClass}>Already in the live prompt</div>
                <ul className="mt-1 space-y-2 rounded-[10px] border border-border bg-[var(--wt-warning-surface)] px-3 py-2">
                  {preview.skipped?.map((item, i) => (
                    <li key={item.id || i} className="text-[12px] leading-relaxed">
                      <p className="font-mono text-[11.5px] break-words">{item.text}</p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {skipReasonLabel(item.reason)} — will not be written again.
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <div className={fieldLabelClass}>
                {preview.unchanged ? "No prompt changes" : "Prompt diff"}
              </div>
              {preview.unchanged ? (
                <p className="mt-1 text-[12.5px] text-muted-foreground">
                  Selected wording is already in the live prompt (or duplicated in this selection).
                </p>
              ) : (
                <PromptDiff hunks={preview.diff ?? []} />
              )}
            </div>
            {error && (
              <p className="text-[12.5px] break-words text-fail">{error}</p>
            )}
          </div>
        ) : (
          <p className="text-[12.5px] leading-relaxed text-muted-foreground">
            {busy
              ? "Loading the live prompt…"
              : error || "Could not load the live prompt."}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            disabled={
              busy ||
              !preview ||
              preview.unchanged ||
              preview.applied_finding_ids.length === 0
            }
          >
            {busy && preview ? "Writing…" : "Write to live agent"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
