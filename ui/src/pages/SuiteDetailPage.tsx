import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Pencil } from "lucide-react";
import { SuiteCasesTable } from "@/components/SuiteCasesTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { client, type SuiteDetail } from "@/lib/api";
import {
  parseConstraints,
  suiteCaseRows,
  type SuiteCaseRow,
} from "@/lib/suiteCases";

export function SuiteDetailPage() {
  const { name = "" } = useParams();
  const [suite, setSuite] = useState<SuiteDetail | null>(null);
  const [rows, setRows] = useState<SuiteCaseRow[]>([]);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [editingTitle, setEditingTitle] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);

  const displayTitle =
    (suite?.title || "").trim() || suite?.name || name;

  useEffect(() => {
    setSuite(null);
    setRows([]);
    setEditing(false);
    setDirty(false);
    setSaved(false);
    setError(null);
    setEditingTitle(false);
    client
      .suite(name)
      .then((s) => {
        setSuite(s);
        setRows(suiteCaseRows(s));
        setTitleDraft((s.title || "").trim() || s.name);
      })
      .catch((e: Error) => setError(e.message));
  }, [name]);

  useEffect(() => {
    if (editingTitle) titleInputRef.current?.focus();
  }, [editingTitle]);

  function patchRow(index: number, patch: Partial<SuiteCaseRow>) {
    setRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
    setDirty(true);
    setSaved(false);
  }

  function startEdit() {
    setEditing(true);
    setSaved(false);
  }

  function cancelEdit() {
    if (suite) setRows(suiteCaseRows(suite));
    setEditing(false);
    setDirty(false);
    setSaved(false);
    setError(null);
  }

  async function saveTitle() {
    const next = titleDraft.trim();
    if (!next || next === displayTitle) {
      setEditingTitle(false);
      setTitleDraft(displayTitle);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await client.updateSuite(name, { title: next });
      setSuite(updated);
      setTitleDraft((updated.title || "").trim() || updated.name);
      setEditingTitle(false);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await client.updateSuite(name, {
        cases: rows.map((r) => ({
          scenario_id: r.scenarioId,
          persona_id: r.personaId,
          name: r.name,
          category: r.category || null,
          identity: r.identity,
          goal: r.goal,
          constraints: parseConstraints(r.constraints),
          max_turns: r.maxTurns,
          success_criteria: r.successCriteria,
          rubric: r.rubric,
        })),
      });
      setSuite(updated);
      setRows(suiteCaseRows(updated));
      setTitleDraft((updated.title || "").trim() || updated.name);
      setDirty(false);
      setEditing(false);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!suite && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/suites"
          className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground"
        >
          ← Test Suites
        </Link>
        <div className="mt-2 flex items-start justify-between gap-5">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex flex-wrap items-baseline gap-2.5">
              {editingTitle ? (
                <Input
                  ref={titleInputRef}
                  value={titleDraft}
                  disabled={busy}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onBlur={() => void saveTitle()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void saveTitle();
                    }
                    if (e.key === "Escape") {
                      setTitleDraft(displayTitle);
                      setEditingTitle(false);
                    }
                  }}
                  className="h-9 max-w-xl text-[22px] font-semibold tracking-[-0.005em]"
                  aria-label="Suite title"
                />
              ) : (
                <button
                  type="button"
                  className="group inline-flex max-w-full items-baseline gap-2 text-left"
                  onClick={() => {
                    setTitleDraft(displayTitle);
                    setEditingTitle(true);
                  }}
                  title="Click to rename"
                >
                  <h1 className="truncate text-[22px] font-semibold tracking-[-0.005em] text-foreground group-hover:underline group-hover:decoration-muted-foreground/40 group-hover:underline-offset-4">
                    {displayTitle}
                  </h1>
                  <Pencil className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              )}
              <span className="font-mono text-[13px] font-medium text-[var(--wt-text-muted)]">
                {rows.length} cases
              </span>
            </div>
            <p className="max-w-2xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
              {editing
                ? "Editing test cases — Save writes back to the suite YAML."
                : (
                  <>
                    Test cases in this suite
                    {suite?.name && suite.name !== displayTitle ? (
                      <>
                        {" "}
                        ·{" "}
                        <span className="font-mono text-[12.5px]">
                          {suite.name}
                        </span>
                      </>
                    ) : null}
                  </>
                )}
            </p>
          </div>
          {editing ? (
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="outline" onClick={cancelEdit} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={save} disabled={busy || !dirty}>
                {busy ? "Saving…" : "Save"}
              </Button>
            </div>
          ) : (
            <Button
              variant="outline"
              onClick={startEdit}
              disabled={!suite}
              className="shrink-0"
            >
              <Pencil data-icon="inline-start" className="size-3.5" />
              Edit
            </Button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-fail">{error}</p>}
      {saved && !editing && !editingTitle && !error && (
        <p className="text-sm text-muted-foreground">Saved.</p>
      )}

      {suite && (
        <SuiteCasesTable
          rows={rows}
          editing={editing}
          onChange={patchRow}
          onRequestEdit={startEdit}
        />
      )}
    </div>
  );
}
