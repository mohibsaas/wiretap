import type { SuiteDetail } from "@/lib/api";

/** One joined scenario + persona row for the suite cases table. */
export type SuiteCaseRow = {
  index: number;
  scenarioId: string;
  personaId: string;
  name: string;
  category: string;
  identity: string;
  goal: string;
  constraints: string;
  maxTurns: number;
  successCriteria: string;
  rubric: string;
};

export function suiteCaseRows(suite: SuiteDetail): SuiteCaseRow[] {
  const personas = new Map(suite.personas.map((p) => [p.id, p]));
  return suite.scenarios.map((sc, i) => {
    const persona = personas.get(sc.persona_id);
    const constraints = Array.isArray(persona?.constraints)
      ? persona!.constraints!.filter(Boolean).join("; ")
      : "";
    return {
      index: i + 1,
      scenarioId: sc.id,
      personaId: sc.persona_id,
      name: sc.name || persona?.name || sc.id,
      category: sc.category || "",
      identity: persona?.identity || "",
      goal: persona?.goal || "",
      constraints,
      maxTurns: sc.max_turns,
      successCriteria: sc.success_criteria || "",
      rubric: sc.rubric || "",
    };
  });
}

export function parseConstraints(raw: string): string[] {
  return raw
    .split(/[;\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}
