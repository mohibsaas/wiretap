import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { NewSuiteDialog } from "@/components/NewSuiteDialog";
import { PageHeader } from "@/components/PageHeader";
import { TruncatedText } from "@/components/TruncatedText";
import { Button } from "@/components/ui/button";
import { client, type SuiteSummary } from "@/lib/api";
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

function suiteTitle(s: SuiteSummary): string {
  return (s.title || "").trim() || s.name;
}

function suiteSubtitle(s: SuiteSummary): string {
  if (s.error) return s.error;
  const parts: string[] = [];
  const title = suiteTitle(s);
  if (title !== s.name) parts.push(s.name);
  if (s.transport) parts.push(s.transport);
  return parts.join(" · ") || "Local suite";
}

export function SuitesPage() {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<SuiteSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  function reload() {
    client
      .suites()
      .then(setSuites)
      .catch((e: Error) => setError(e.message));
  }

  useEffect(() => {
    reload();
  }, []);

  const meta = useMemo(() => {
    const n = suites.length;
    return `${n} suite${n === 1 ? "" : "s"}`;
  }, [suites.length]);

  async function confirmDelete() {
    const s = pendingDelete;
    if (!s) return;
    setDeleting(true);
    setError(null);
    try {
      await client.deleteSuite(s.name);
      setPendingDelete(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Test Suites"
        meta={meta}
        subtitle="Local suites under .wiretap/suites/."
        action={
          <Button className="rounded-full" onClick={() => setCreateOpen(true)}>
            <Plus data-icon="inline-start" />
            New suite
          </Button>
        }
      />

      {error && <p className="text-sm text-fail">{error}</p>}

      <div className="overflow-x-auto rounded-[14px] border border-border bg-card">
        <div className="min-w-[560px]">
          <div
            className="grid gap-0 border-b border-border bg-[var(--wt-section)] px-5 py-2.5 text-[10.5px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase"
            style={{
              gridTemplateColumns: "minmax(220px,1.8fr) 140px 100px 56px",
            }}
          >
            <div>Suite</div>
            <div>Provider</div>
            <div>Cases</div>
            <div className="text-right"> </div>
          </div>

          {suites.length === 0 && !error ? (
            <div className="px-5 py-10 text-sm text-muted-foreground text-pretty">
              No suites yet.{" "}
              <button
                type="button"
                className="font-medium text-foreground underline-offset-2 hover:underline"
                onClick={() => setCreateOpen(true)}
              >
                Create one
              </button>{" "}
              or run{" "}
              <code className="font-mono text-[12.5px]">wiretap import</code>.
            </div>
          ) : (
            suites.map((s) => {
              const title = suiteTitle(s);
              const cases = s.scenario_count ?? 0;
              const invalid = Boolean(s.error);
              return (
                <div
                  key={s.name}
                  className="grid items-center gap-0 border-b border-border px-5 py-3.5 last:border-b-0 transition-colors hover:bg-[var(--wt-section)]"
                  style={{
                    gridTemplateColumns: "minmax(220px,1.8fr) 140px 100px 56px",
                  }}
                >
                  <div className="min-w-0 pr-3">
                    {invalid ? (
                      <>
                        <TruncatedText
                          text={title}
                          className="text-[13.5px] font-semibold leading-snug text-foreground"
                        />
                        <TruncatedText
                          text={suiteSubtitle(s)}
                          className="mt-0.5 text-xs leading-snug text-fail"
                        />
                      </>
                    ) : (
                      <Link
                        to={`/suites/${encodeURIComponent(s.name)}`}
                        className="block min-w-0"
                      >
                        <TruncatedText
                          text={title}
                          className="text-[13.5px] font-semibold leading-snug text-foreground underline-offset-2 hover:underline"
                        />
                        <TruncatedText
                          text={suiteSubtitle(s)}
                          className="mt-0.5 text-xs leading-snug text-[var(--wt-text-muted)]"
                        />
                      </Link>
                    )}
                  </div>

                  <div className="min-w-0 pr-3 text-[13px] text-muted-foreground">
                    <TruncatedText text={providerLabel(s.platform)} />
                  </div>

                  <div
                    className={cn(
                      "pr-3 font-mono text-[12.5px] tabular-nums",
                      invalid
                        ? "text-muted-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {invalid ? "—" : cases}
                  </div>

                  <div className="flex justify-end">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      disabled={deleting}
                      aria-label={`Delete ${title}`}
                      onClick={() => setPendingDelete(s)}
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

      <NewSuiteDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        existingNames={suites.map((s) => s.name)}
        onCreated={() => reload()}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) setPendingDelete(null);
        }}
        title="Delete suite?"
        description={
          pendingDelete
            ? `Delete suite “${suiteTitle(pendingDelete)}” (${pendingDelete.name})? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
