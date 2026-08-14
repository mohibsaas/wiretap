import { useEffect, useState } from "react";
import {
  BookOpen,
  Check,
  Heart,
  Scale,
  Settings2,
  Shield,
  Text,
  Shapes,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { client, type Category } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Soft tile colors from the wiretap-ui Test Categories reference. */
const CATEGORY_TILE: Record<
  string,
  { bg: string; fg: string; Icon: LucideIcon }
> = {
  emotional: { bg: "#FEE9E9", fg: "#B54444", Icon: Heart },
  linguistic: { bg: "#EEEAF7", fg: "#6B4EA8", Icon: Text },
  adversarial: { bg: "#F7EAEA", fg: "#A73535", Icon: Shield },
  operational: { bg: "#E6F0F7", fg: "#2F6B9E", Icon: Settings2 },
  factual: { bg: "#EFF3E6", fg: "#5C7A2E", Icon: BookOpen },
  compliance: { bg: "#F7F0E6", fg: "#8A5B12", Icon: Scale },
  task: { bg: "#E6EEE7", fg: "#056938", Icon: Check },
  other: { bg: "#F2F1EE", fg: "#747370", Icon: Shapes },
};

function tileFor(id: string) {
  return CATEGORY_TILE[id] || CATEGORY_TILE.other;
}

export function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    client
      .categories()
      .then((rows) => {
        if (!live) return;
        setCategories(Array.isArray(rows) ? rows : []);
      })
      .catch((e: Error) => {
        if (!live) return;
        setError(e.message);
        setCategories([]);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-8 pb-10">
      <PageHeader
        title="Test Categories"
        meta={
          !loading && categories.length
            ? `${categories.length} categor${categories.length === 1 ? "y" : "ies"}`
            : undefined
        }
        subtitle="The fixed set of behaviors Wiretap can generate and grade. Examples below are style seeds for suite generation — not your live suite content."
      />

      {error && <p className="text-sm text-fail">{error}</p>}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading categories…</p>
      ) : !error && categories.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No categories returned from the API.
        </p>
      ) : (
        <div className="flex flex-col gap-8">
          {categories.map((cat) => {
            const examples = Array.isArray(cat.examples) ? cat.examples : [];
            const tile = tileFor(cat.id);
            const Icon = tile.Icon;
            return (
              <section key={cat.id} className="flex flex-col gap-3">
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-baseline gap-2.5">
                    <h2 className="text-[17px] font-semibold tracking-[-0.005em] text-foreground">
                      {cat.label}
                    </h2>
                    <span className="font-mono text-[12.5px] text-[var(--wt-text-muted)]">
                      {examples.length
                        ? `${examples.length} example${examples.length === 1 ? "" : "s"}`
                        : cat.id}
                    </span>
                  </div>
                  <p className="max-w-3xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
                    {cat.description}
                  </p>
                </div>

                {examples.length > 0 ? (
                  <div className="overflow-hidden rounded-[14px] border border-border bg-card">
                    {examples.map((ex, i) => {
                      const hint = ex.goal || ex.identity;
                      const opener = ex.say;
                      return (
                        <div
                          key={`${cat.id}-${ex.name || i}`}
                          className={cn(
                            "flex items-start gap-3.5 px-[18px] py-3.5 transition-colors hover:bg-[var(--wt-section)]",
                            i > 0 && "border-t border-border",
                          )}
                        >
                          <span
                            className="inline-flex size-[34px] shrink-0 items-center justify-center rounded-[9px]"
                            style={{ background: tile.bg, color: tile.fg }}
                            aria-hidden
                          >
                            <Icon className="size-4" strokeWidth={1.8} />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="text-[14.5px] font-semibold leading-snug text-foreground">
                              {ex.name || "Untitled example"}
                            </div>
                            {hint ? (
                              <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground text-pretty">
                                {hint}
                              </p>
                            ) : null}
                            {opener ? (
                              <p className="mt-0.5 text-[12.5px] leading-relaxed text-[var(--wt-text-muted)] text-pretty">
                                Opens with “{opener}”
                              </p>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-[14px] border border-border bg-[var(--wt-section)] px-5 py-4 text-sm text-muted-foreground">
                    No example seeds for this category yet.
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
