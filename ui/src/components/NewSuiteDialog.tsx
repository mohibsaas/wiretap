import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { client, type Category, type SuiteSummary } from "@/lib/api";
import {
  AppModal,
  modalFieldClass,
  modalFieldsClass,
  modalHintClass,
  modalInputClass,
  modalLabelClass,
} from "@/components/AppModal";
import { AppSelect } from "@/components/AppSelect";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Mode = "generate" | "blank";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existingNames?: string[];
  onCreated?: (suiteName: string) => void;
};

function suiteSlug(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
}

/**
 * Create a suite by LLM generation (categories) or as a blank shell
 * for adding cases one-by-one on the detail page.
 */
export function NewSuiteDialog({
  open,
  onOpenChange,
  existingNames = [],
  onCreated,
}: Props) {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("generate");
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [selected, setSelected] = useState<string[]>([
    "emotional",
    "compliance",
    "task",
  ]);
  const [perCat, setPerCat] = useState(3);
  const [agentFrom, setAgentFrom] = useState("");
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [genProgress, setGenProgress] = useState<{
    detail: string;
    done: number;
    total: number;
  } | null>(null);

  const taken = useMemo(
    () => new Set(existingNames.map((n) => n.toLowerCase())),
    [existingNames],
  );

  const stem = useMemo(() => {
    const fromTitle = suiteSlug(title);
    return fromTitle || "new_suite";
  }, [title]);

  const nameTaken = taken.has(stem.toLowerCase());

  const selectedLabels = useMemo(
    () =>
      selected.map(
        (id) => categories.find((c) => c.id === id)?.label || id,
      ),
    [selected, categories],
  );

  const expectedTotal = selected.length * perCat;

  useEffect(() => {
    if (!open) return;
    setMode("generate");
    setTitle("");
    setPurpose("");
    setSelected(["emotional", "compliance", "task"]);
    setPerCat(3);
    setAgentFrom("");
    setBusy(false);
    setError(null);
    setGenProgress(null);
    void client.categories().then(setCategories).catch(() => setCategories([]));
    void client
      .suites()
      .then((rows) => setSuites(rows.filter((s) => !s.error)))
      .catch(() => setSuites([]));
  }, [open]);

  // Soft paced status while the generate request is in flight (API is one-shot).
  useEffect(() => {
    if (!busy || mode !== "generate") {
      setGenProgress(null);
      return;
    }
    const labels = selectedLabels.length
      ? selectedLabels
      : ["scenarios"];
    const total = Math.max(1, expectedTotal);
    let step = 0;
    setGenProgress({
      detail: `Starting ${labels[0].toLowerCase()}…`,
      done: 0,
      total,
    });
    const id = window.setInterval(() => {
      step += 1;
      const done = Math.min(total - 1, step);
      const catIdx = Math.min(
        labels.length - 1,
        Math.floor((done / total) * labels.length),
      );
      const label = labels[catIdx];
      setGenProgress({
        detail:
          done === 0
            ? `Starting ${label.toLowerCase()}…`
            : `Writing ${label.toLowerCase()} cases…`,
        done,
        total,
      });
    }, 1100);
    return () => window.clearInterval(id);
  }, [busy, mode, selectedLabels, expectedTotal]);

  function toggleCat(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id],
    );
  }

  async function submit() {
    if (!title.trim()) {
      setError("Give the suite a name.");
      return;
    }
    if (nameTaken) {
      setError(`A suite named “${stem}” already exists.`);
      return;
    }
    if (mode === "generate" && selected.length === 0) {
      setError("Pick at least one category.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      let suiteName = stem;
      if (mode === "blank") {
        const created = await client.createSuite({
          name: stem,
          title: title.trim(),
          agent_from: agentFrom || null,
        });
        suiteName = created.name;
      } else {
        setGenProgress({
          detail: "Finishing suite…",
          done: Math.max(0, expectedTotal - 1),
          total: Math.max(1, expectedTotal),
        });
        const res = await client.generate({
          purpose: purpose.trim(),
          categories: selected,
          tests_per_category: perCat,
          suite_name: stem,
        });
        suiteName = res.suite_name;
        setGenProgress({
          detail: "Suite ready",
          done: Math.max(1, expectedTotal),
          total: Math.max(1, expectedTotal),
        });
        if (title.trim() && title.trim() !== suiteName) {
          await client.updateSuite(suiteName, { title: title.trim() });
        }
      }
      onOpenChange(false);
      onCreated?.(suiteName);
      navigate(`/suites/${encodeURIComponent(suiteName)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setGenProgress(null);
    }
  }

  const generating = busy && mode === "generate";

  return (
    <AppModal
      open={open}
      onOpenChange={(next) => {
        if (!next && busy) return;
        onOpenChange(next);
      }}
      title="New test suite"
      description="Generate cases from categories, or start blank and add tests one by one."
      maxWidthClass="sm:max-w-[520px]"
      footer={
        <>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={
              busy ||
              !title.trim() ||
              nameTaken ||
              (mode === "generate" && selected.length === 0)
            }
          >
            {busy
              ? mode === "generate"
                ? "Generating…"
                : "Creating…"
              : mode === "generate"
                ? "Generate suite"
                : "Create blank suite"}
          </Button>
        </>
      }
    >
      <div
        className={cn(
          "inline-flex w-fit rounded-[10px] border border-border bg-[var(--wt-section)] p-0.5",
          busy && "pointer-events-none opacity-50",
        )}
      >
        <button
          type="button"
          className={cn(
            "rounded-[8px] px-3 py-1.5 text-[13px] font-medium transition-colors",
            mode === "generate"
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
          onClick={() => setMode("generate")}
        >
          Generate
        </button>
        <button
          type="button"
          className={cn(
            "rounded-[8px] px-3 py-1.5 text-[13px] font-medium transition-colors",
            mode === "blank"
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
          onClick={() => setMode("blank")}
        >
          Blank suite
        </button>
      </div>

      <div
        className={cn(modalFieldsClass, busy && "pointer-events-none opacity-60")}
      >
        <div className={modalFieldClass}>
          <Label htmlFor="suite-title" className={modalLabelClass}>
            Name
          </Label>
          <Input
            id="suite-title"
            className={modalInputClass}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Booking edge cases"
            disabled={busy}
          />
          <p className="font-mono text-[11.5px] text-[var(--wt-text-muted)]">
            id · {stem}
            {nameTaken ? " · already taken" : ""}
          </p>
        </div>

        {mode === "blank" && suites.length > 0 ? (
          <div className={modalFieldClass}>
            <Label htmlFor="suite-agent-from" className={modalLabelClass}>
              Bind agent (optional)
            </Label>
            <AppSelect
              id="suite-agent-from"
              value={agentFrom || "__default__"}
              onValueChange={(v) =>
                setAgentFrom(v === "__default__" ? "" : v)
              }
              disabled={busy}
              options={[
                { value: "__default__", label: "Workspace default" },
                ...suites.map((s) => ({
                  value: s.name,
                  label:
                    ((s.title || "").trim() || s.name) +
                    (s.platform ? ` · ${s.platform}` : ""),
                })),
              ]}
            />
          </div>
        ) : null}

        {mode === "generate" ? (
          <>
            <div className={modalFieldClass}>
              <Label htmlFor="suite-purpose" className={modalLabelClass}>
                Purpose (optional)
              </Label>
              <Input
                id="suite-purpose"
                className={modalInputClass}
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="e.g. cancellation and refund flows"
                disabled={busy}
              />
            </div>

            <div className="flex min-w-0 flex-col gap-1.5">
              <Label className={modalLabelClass}>Categories</Label>
              <div className="max-h-48 overflow-y-auto rounded-[10px] border border-border">
                {categories.map((c, i) => (
                  <label
                    key={c.id}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 px-3 py-2.5 text-sm hover:bg-[var(--wt-section)]",
                      i > 0 && "border-t border-border",
                    )}
                  >
                    <Checkbox
                      checked={selected.includes(c.id)}
                      onCheckedChange={() => toggleCat(c.id)}
                      className="mt-0.5"
                      disabled={busy}
                    />
                    <span className="min-w-0">
                      <span className="font-medium text-foreground">
                        {c.label}
                      </span>
                      <span className="mt-0.5 block text-[12.5px] leading-snug text-muted-foreground">
                        {c.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className={modalFieldClass}>
              <Label htmlFor="suite-per-cat" className={modalLabelClass}>
                Cases per category
              </Label>
              <Input
                id="suite-per-cat"
                type="number"
                min={1}
                max={10}
                className={cn(modalInputClass, "w-24")}
                value={perCat}
                disabled={busy}
                onChange={(e) =>
                  setPerCat(
                    Math.min(10, Math.max(1, Number(e.target.value) || 1)),
                  )
                }
              />
              <p className={modalHintClass}>
                About {selected.length * perCat} scenarios
              </p>
            </div>
          </>
        ) : (
          <p className="text-[13px] leading-relaxed text-muted-foreground">
            Creates an empty suite. On the next page you can add test cases one
            by one and edit them inline.
          </p>
        )}

        {error && <p className="text-sm text-fail">{error}</p>}
      </div>

      {generating && genProgress ? (
        <div className="rounded-[10px] border border-border bg-[var(--wt-section)] px-3.5 py-3">
          <div className="flex items-baseline justify-between gap-3">
            <p className="min-w-0 truncate text-[12.5px] text-muted-foreground">
              {genProgress.detail}
            </p>
            <p className="shrink-0 font-mono text-[11.5px] tabular-nums text-[var(--wt-text-muted)]">
              {genProgress.done}/{genProgress.total}
            </p>
          </div>
          <div className="mt-2.5 h-[3px] overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full bg-primary/65 transition-[width] duration-700 ease-out"
              style={{
                width: `${Math.max(
                  8,
                  Math.round((genProgress.done / genProgress.total) * 100),
                )}%`,
              }}
            />
          </div>
        </div>
      ) : null}
    </AppModal>
  );
}
