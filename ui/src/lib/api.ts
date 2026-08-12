export type SuiteSummary = {
  name: string;
  path: string;
  scenario_count?: number;
  persona_count?: number;
  platform?: string | null;
  transport?: string;
  error?: string;
};

export type SuiteDetail = {
  name: string;
  agent: {
    transport: string;
    platform?: string | null;
    agent_id?: string | null;
    token_env?: string | null;
  };
  personas: { id: string; name?: string; identity: string; goal: string }[];
  scenarios: {
    id: string;
    name: string;
    persona_id: string;
    max_turns: number;
    success_criteria: string;
    category?: string | null;
  }[];
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
  transcript: { role: string; text: string }[];
  judge: { passed: boolean; reason: string; suggestions: string[] };
  rules: { passed: boolean; failures: string[] };
  meta: Record<string, unknown>;
  audio_path?: string | null;
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
};

export type Batch = {
  batch_id: string;
  suite: string;
  status: string;
  scenario_ids: string[];
  results: Simulation[];
  error?: string | null;
};

export type Category = {
  id: string;
  label: string;
  description: string;
  max_tests: number;
};

export type ProviderInfo = {
  id: string;
  label: string;
  kind: string;
  env: string;
  default_model?: string | null;
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
  providers: () => api<ProviderCatalog>("/api/providers"),
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
  }) =>
    api<{
      platform: string;
      agent_id?: string;
      agent_name?: string;
      suite_name?: string;
      imported: boolean;
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
  agents: () => api<AgentRow[]>("/api/agents"),
  suites: () => api<SuiteSummary[]>("/api/suites"),
  suite: (name: string) => api<SuiteDetail>(`/api/suites/${name}`),
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
  }) =>
    api<{ batch_id: string }>("/api/batches", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  batch: (id: string) => api<Batch>(`/api/batches/${id}`),
};
