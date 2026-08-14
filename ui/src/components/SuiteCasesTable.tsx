import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";
import type { SuiteCaseRow } from "@/lib/suiteCases";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const COLS =
  "grid-cols-[48px_minmax(160px,200px)_120px_minmax(140px,200px)_minmax(180px,1fr)_minmax(180px,1fr)_minmax(140px,0.9fr)_72px]";

/** Invisible chrome so edit controls occupy the same box as plain text. */
const quietField =
  "m-0 box-border block w-full min-w-0 appearance-none border-0 bg-transparent p-0 shadow-none outline-none ring-0 rounded-sm resize-none overflow-hidden align-top focus-visible:bg-[var(--wt-section)]/55";

type Props = {
  rows: SuiteCaseRow[];
  editing?: boolean;
  onChange?: (index: number, patch: Partial<SuiteCaseRow>) => void;
  onRequestEdit?: () => void;
};

export function SuiteCasesTable({
  rows,
  editing = false,
  onChange,
  onRequestEdit,
}: Props) {
  return (
    <div className="overflow-hidden rounded-[14px] border border-border bg-card">
      <div className="overflow-x-auto">
        <div className="min-w-[1180px]">
          <div
            className={cn(
              "grid items-center gap-x-3 border-b border-border bg-[var(--wt-section)] px-5 py-2.5 text-[10.5px] font-semibold tracking-[0.06em] text-muted-foreground uppercase",
              COLS,
            )}
          >
            <div>#</div>
            <div>Persona</div>
            <div>Category</div>
            <div>ID</div>
            <div>Identity</div>
            <div>Goal</div>
            <div>Constraints</div>
            <div>Max turns</div>
          </div>
          {rows.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No test cases in this suite.
            </div>
          ) : (
            rows.map((row, i) => (
              <div
                key={row.scenarioId}
                onDoubleClick={() => {
                  if (!editing) onRequestEdit?.();
                }}
                className={cn(
                  "grid items-start gap-x-3 border-b border-border px-5 py-3.5 last:border-b-0",
                  COLS,
                  !editing && "hover:bg-[var(--wt-section)]",
                )}
                title={!editing && onRequestEdit ? "Double-click to edit" : undefined}
              >
                <div className="font-mono text-[12.5px] leading-snug text-muted-foreground">
                  #{row.index}
                </div>

                <Cell
                  editing={editing}
                  value={row.name}
                  className="text-[13.5px] font-semibold leading-snug text-foreground"
                  onChange={(v) => onChange?.(i, { name: v })}
                />

                <div className="min-w-0 leading-snug">
                  {editing ? (
                    <Badge
                      variant="muted"
                      className="max-w-full font-normal normal-case"
                    >
                      <input
                        value={row.category}
                        onChange={(e) =>
                          onChange?.(i, { category: e.target.value })
                        }
                        className={cn(
                          quietField,
                          "min-w-[4ch] bg-transparent text-[11.5px] leading-none text-muted-foreground",
                        )}
                        size={Math.max(4, row.category.length || 4)}
                        aria-label="Category"
                      />
                    </Badge>
                  ) : row.category ? (
                    <Badge variant="muted" className="font-normal">
                      {row.category}
                    </Badge>
                  ) : (
                    <span className="text-[12.5px] leading-snug text-muted-foreground">
                      —
                    </span>
                  )}
                </div>

                <div className="break-all font-mono text-xs leading-snug text-muted-foreground">
                  {row.scenarioId}
                </div>

                <Cell
                  editing={editing}
                  value={row.identity}
                  onChange={(v) => onChange?.(i, { identity: v })}
                />
                <Cell
                  editing={editing}
                  value={row.goal}
                  onChange={(v) => onChange?.(i, { goal: v })}
                />
                <Cell
                  editing={editing}
                  value={row.constraints}
                  onChange={(v) => onChange?.(i, { constraints: v })}
                />

                <div className="font-mono text-[12.5px] leading-snug tabular-nums">
                  {editing ? (
                    <input
                      type="number"
                      min={1}
                      max={200}
                      value={row.maxTurns}
                      onChange={(e) =>
                        onChange?.(i, {
                          maxTurns: Math.max(1, Number(e.target.value) || 1),
                        })
                      }
                      className={cn(
                        quietField,
                        "w-full font-mono text-[12.5px] leading-snug tabular-nums text-foreground [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none",
                      )}
                      aria-label="Max turns"
                    />
                  ) : (
                    row.maxTurns
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Cell({
  value,
  editing,
  className,
  onChange,
}: {
  value: string;
  editing?: boolean;
  className?: string;
  onChange?: (value: string) => void;
}) {
  const textClass = cn(
    "text-[12.5px] leading-relaxed text-muted-foreground",
    className,
  );

  if (!editing) {
    return <div className={cn("min-w-0", textClass)}>{value || "—"}</div>;
  }

  return (
    <AutoTextarea
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      className={cn(quietField, textClass)}
      aria-label="Edit cell"
    />
  );
}

/** Grows with content so edit height matches wrapped view text. */
function AutoTextarea({
  value,
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <textarea
      {...rest}
      ref={ref}
      value={value}
      rows={1}
      className={cn(className, "[field-sizing:content]")}
    />
  );
}
