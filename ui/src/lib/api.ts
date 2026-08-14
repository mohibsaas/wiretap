export type SuiteSummary = {
  name: string;
  title?: string;
  path: string;
  scenario_count?: number;
  persona_count?: number;
  platform?: string | null;
  transport?: string;
  error?: string;
};

export type SuiteDetail = {
  name: string;
  title?: string;
  agent: {
    transport: string;
    platform?: string | null;
    agent_id?: string | null;
    token_env?: string | null;
  };
  personas: {
    id: string;
    name?: string;
    identity: string;
    goal: string;
    constraints?: string[];
    personality?: string;
  }[];
  scenarios: {
    id: string;
    name: string;
    persona_id: string;
    max_turns: number;
    success_criteria: string;
    rubric?: string;
    category?: string | null;
  }[];
};

export type SuiteCaseUpdate = {
  scenario_id: string;
  persona_id: string;
  name: string;
  category?: string | null;
  identity: string;
  goal: string;
  constraints: string[];
  max_turns: number;
  success_criteria?: string | null;
  rubric?: string | null;
};

export type JudgeMetric = {
  id: string;
  score: number;
  passed: boolean;
  threshold: number;
  required?: boolean;
  weight?: number;
  rationale?: string;
};

export type ToolCall = {
  name: string;
  arguments: Record<string, unknown>;
  result_summary: string;
  status: string;
  turn_index: number | null;
  at_seconds: number | null;
};

export type Simulation = {
  simulation_id: string;
  created_at: string;
  batch_id?: string;
  suite_id: string;
  scenario_id: string;
  scenario_name?: string;
  persona_id: string;
  persona_name?: string;
  passed: boolean;
  transcript: {
    role: string;
    text: string;
    start_ms?: number | null;
    end_ms?: number | null;
  }[];
  tool_calls?: ToolCall[];
  judge: {
    passed: boolean;
    reason: string;
    suggestions: string[];
    metrics?: JudgeMetric[];
    score?: number | null;
    verdict?: string | null;
    fail_below?: number | null;
    pass_at?: number | null;
    pass_mode?: string | null;
  };
  rules: { passed: boolean; failures: string[] };
  metrics?: Record<string, unknown>;
  meta: Record<string, unknown>;
  audio_path?: string | null;
};

export type AdviceTarget =
  | "agent_prompt"
  | "tools"
  | "flow"
  | "voice_runtime"
  | "test_suite";

export type AdviceFinding = {
  id: string;
  target: AdviceTarget | string;
  severity: "high" | "medium" | "low" | string;
  title: string;
  problem?: string;
  recommendation?: string;
  /** Drop-in prompt wording. Empty when the agent config was not importable. */
  suggested_text?: string;
  evidence?: { scenario_id?: string; quote: string }[];
  affected_scenarios?: string[];
  confidence?: "high" | "medium" | "low" | string;
};

/** Run-level agent-improvement advice, generated once per evaluation run. */
export type RunAdvice = {
  summary?: string;
  findings: AdviceFinding[];
  model?: string;
  generated_at?: string;
  grounding?: "config" | "behavior_only" | string;
  based_on_scenarios?: string[];
  error?: string;
};

export type EvaluationRun = {
  batch_id: string;
  suite_id: string;
  created_at?: string;
  finished_at?: string | null;
  status?: string;
  error?: string | null;
  scenario_ids?: string[];
  simulation_ids?: string[];
  passed: number;
  failed: number;
  inconclusive?: number;
  total: number;
  concurrency?: number;
  simulations?: Simulation[];
  advice?: RunAdvice | null;
};

export type Batch = {
  batch_id: string;
  suite: string;
  status: string;
  scenario_ids: string[];
  results: Simulation[];
  error?: string | null;
  advice?: RunAdvice | null;
};

export type Category = {
  id: string;
  label: string;
  description: string;
  max_tests: number;
  examples?: {
    name: string;
    identity: string;
    goal: string;
    say: string;
  }[];
};

export type VoiceOption = {
  id: string;
  label: string;
};

export type ProviderInfo = {
  id: string;
  label: string;
  kind: string;
  env: string;
  default_model?: string | null;
  models?: string[];
  default_voice?: string | null;
  voices?: VoiceOption[];
};

export type ProviderCatalog = {
  defaults: { llm: string; stt: string; tts: string; voice: string };
  llm: ProviderInfo[];
  stt: ProviderInfo[];
  tts: ProviderInfo[];
};

export type CallerConfig = {
  llm_provider: string;
  simulator_model: string;
  judge_model: string;
  stt: string;
  tts: string;
  voice: string;
};

export type OnboardStatus = {
  completed: boolean;
  caller_configured?: boolean;
  needs_onboarding: boolean;
  has_llm_key: boolean;
  has_speech_key?: boolean;
  has_platform_key: boolean;
  platform?: string;
  agent_id?: string;
  agent_name?: string;
  purpose?: string;
  suite_name?: string;
  categories?: string[];
  suite_count: number;
  keys: Record<string, boolean>;
  caller?: CallerConfig;
  providers?: ProviderCatalog;
  categories_catalog: Category[];
};

export type PstnStatus = {
  ready: boolean;
  extra_installed: boolean;
  missing_packages: string[];
  has_credentials: boolean;
  from_number?: string | null;
  missing: string[];
  keys: Record<string, boolean>;
};

export type TwilioNumber = {
  phone_number: string;
  friendly_name?: string;
};

/** The agent's own number a phone run would dial, and where it came from. */
export type AgentNumberTarget = {
  number: string | null;
  source: "request" | "suite" | "saved" | null;
};

export type AgentRow = {
  id?: string;
  agent_id?: string | null;
  suite?: string | null;
  platform?: string | null;
  transport?: string;
  name?: string;
  scenario_count?: number;
  connected?: boolean;
  token_env?: string | null;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const client = {
  health: () => api<{ version: string }>("/api/health"),
  onboardStatus: () => api<OnboardStatus>("/api/onboard/status"),
  categories: () => api<Category[]>("/api/categories"),
  providers: () => api<ProviderCatalog>("/api/providers"),
  llmModels: (provider: string, apiKey?: string | null) =>
    api<{
      provider: string;
      models: string[];
      default_model: string;
      source: "live" | "curated";
      live_supported: boolean;
      error?: string | null;
    }>(`/api/providers/llm/${encodeURIComponent(provider)}/models`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey?.trim() || null }),
    }),
  ttsVoices: (provider: string, apiKey?: string | null) =>
    api<{
      provider: string;
      voices: VoiceOption[];
      default_voice: string;
      source: "live" | "curated";
      live_supported: boolean;
      error?: string | null;
    }>(`/api/providers/tts/${encodeURIComponent(provider)}/voices`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey?.trim() || null }),
    }),
  platformAgents: (platform: string, apiKey?: string | null) =>
    api<{
      platform: string;
      agents: { id: string; name: string; label: string }[];
      source: "live" | "unavailable";
      live_supported: boolean;
      error?: string | null;
    }>(`/api/platforms/${encodeURIComponent(platform)}/agents`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey?.trim() || null }),
    }),
  configureCaller: (body: {
    llm_provider?: string;
    llm_api_key?: string | null;
    simulator_model?: string;
    judge_model?: string;
    stt?: string;
    tts?: string;
    voice?: string;
    speech_api_key?: string | null;
    stt_api_key?: string | null;
    tts_api_key?: string | null;
  }) =>
    api<{ caller: CallerConfig; keys: Record<string, boolean> }>("/api/onboard/caller", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  connect: (body: {
    platform: string;
    agent_id?: string | null;
    api_key?: string | null;
    api_secret?: string | null;
    room_url?: string | null;
  }) =>
    api<{
      platform: string;
      agent_id?: string;
      agent_name?: string;
      suite_name?: string;
      imported: boolean;
      live_deferred?: boolean;
    }>("/api/onboard/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  generate: (body: {
    purpose?: string;
    categories: string[];
    tests_per_category?: number;
    suite_name?: string | null;
  }) =>
    api<{
      suite_name: string;
      path: string;
      scenario_count: number;
      categories: string[];
    }>("/api/onboard/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // Secrets are write-only: the API answers with presence, never values.
  secretsStatus: () => api<Record<string, boolean>>("/api/secrets/status"),
  saveSecrets: (secrets: Record<string, string>) =>
    api<{ updated: string[]; status: Record<string, boolean> }>("/api/secrets", {
      method: "POST",
      body: JSON.stringify({ secrets }),
    }),
  pstnStatus: () => api<PstnStatus>("/api/pstn/status"),
  pstnAgentNumber: (suite: string, agentFrom?: string | null) => {
    const params = new URLSearchParams({ suite });
    if (agentFrom?.trim()) params.set("agent_from", agentFrom.trim());
    return api<AgentNumberTarget>(`/api/pstn/agent-number?${params.toString()}`);
  },
  twilioNumbers: (opts?: { limit?: number; contains?: string | null }) => {
    const params = new URLSearchParams({ limit: String(opts?.limit ?? 20) });
    if (opts?.contains?.trim()) params.set("contains", opts.contains.trim());
    return api<{ numbers: TwilioNumber[]; selected: string | null }>(
      `/api/twilio/phone-numbers?${params.toString()}`,
    );
  },
  saveFromNumber: (fromNumber: string) =>
    api<{ selected: string }>("/api/twilio/from-number", {
      method: "POST",
      body: JSON.stringify({ from_number: fromNumber }),
    }),
  agents: () => api<AgentRow[]>("/api/agents"),
  suites: () => api<SuiteSummary[]>("/api/suites"),
  suite: (name: string) => api<SuiteDetail>(`/api/suites/${encodeURIComponent(name)}`),
  updateSuite: (
    name: string,
    body: { cases?: SuiteCaseUpdate[]; title?: string },
  ) =>
    api<SuiteDetail>(`/api/suites/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteSuite: (name: string) =>
    api<{ name: string; removed: string[] }>(
      `/api/suites/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),
  evaluations: (limit = 40) =>
    api<EvaluationRun[]>(`/api/evaluations?limit=${limit}`),
  evaluation: (batchId: string) =>
    api<EvaluationRun>(`/api/evaluations/${batchId}`),
  simulations: (limit = 40) =>
    api<Simulation[]>(`/api/simulations?limit=${limit}`),
  simulation: (id: string) => api<Simulation>(`/api/simulations/${id}`),
  startBatch: (body: {
    suite: string;
    all?: boolean;
    scenario?: string | null;
    concurrency?: number;
    strict?: boolean;
    agent_id?: string | null;
    platform?: string | null;
    token_env?: string | null;
    agent_from?: string | null;
    transport?: string | null;
    phone?: string | null;
  }) =>
    api<{ batch_id: string }>("/api/batches", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  batch: (id: string) => api<Batch>(`/api/batches/${id}`),
};
