import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Pencil } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { SuiteCasesTable } from "@/components/SuiteCasesTable";
import { Button } from "@/components/ui/button";
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

  useEffect(() => {
    setSuite(null);
    setRows([]);
    setEditing(false);
    setDirty(false);
    setSaved(false);
    setError(null);
    client
      .suite(name)
      .then((s) => {
        setSuite(s);
        setRows(suiteCaseRows(s));
      })
      .catch((e: Error) => setError(e.message));
  }, [name]);

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

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await client.updateSuite(
        name,
        rows.map((r) => ({
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
      );
      setSuite(updated);
      setRows(suiteCaseRows(updated));
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
        <PageHeader
          className="mt-2"
          title={name}
          subtitle={
            editing
              ? "Editing test cases — Save writes back to the suite YAML."
              : "Test cases in this suite"
          }
          meta={`${rows.length} cases`}
          action={
            editing ? (
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={cancelEdit} disabled={busy}>
                  Cancel
                </Button>
                <Button onClick={save} disabled={busy || !dirty}>
                  {busy ? "Saving…" : "Save"}
                </Button>
              </div>
            ) : (
              <Button variant="outline" onClick={startEdit} disabled={!suite}>
                <Pencil data-icon="inline-start" className="size-3.5" />
                Edit
              </Button>
            )
          }
        />
      </div>

      {error && <p className="text-sm text-fail">{error}</p>}
      {saved && !editing && !error && (
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
