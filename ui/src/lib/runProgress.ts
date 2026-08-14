/** Human labels + “still running?” for simulation progress phases. */

export type ScenarioProgress = {
  scenario_id: string;
  scenario_name?: string;
  phase: string;
  detail?: string;
  turn?: number;
  simulation_id?: string | null;
  passed?: boolean | null;
  inconclusive?: boolean | null;
  error?: string | null;
};

export type RunProgress = {
  batch_id: string;
  suite_id?: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  concurrency?: number;
  total?: number;
  done?: number;
  scenarios: ScenarioProgress[];
};

const ACTIVE = new Set([
  "queued",
  "connecting",
  "waiting_agent",
  "turn",
  "hanging_up",
  "judging",
  "saving",
]);

export function phaseIsActive(phase: string | undefined): boolean {
  return ACTIVE.has((phase || "").toLowerCase());
}

export function phaseLabel(phase: string | undefined, turn?: number): string {
  switch ((phase || "").toLowerCase()) {
    case "queued":
      return "Waiting";
    case "connecting":
      return "Connecting";
    case "waiting_agent":
      return "Waiting for agent";
    case "turn":
      return turn && turn > 0 ? `Turn ${turn}` : "In call";
    case "hanging_up":
      return "Ending call";
    case "judging":
      return "Judging";
    case "saving":
      return "Saving";
    case "finished":
      return "Done";
    case "failed":
      return "Failed";
    default:
      return phase || "Running";
  }
}
