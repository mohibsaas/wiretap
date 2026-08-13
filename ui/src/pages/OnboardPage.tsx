import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  client,
  type Category,
  type OnboardStatus,
  type ProviderInfo,
  type ProviderCatalog,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Step = 1 | 2;

function envLabel(p?: ProviderInfo) {
  return p?.env || "API key";
}

export function OnboardPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const addAgentMode = params.get("again") === "1";

  const [step, setStep] = useState<Step>(1);
  const [status, setStatus] = useState<OnboardStatus | null>(null);
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);
  const [showModels, setShowModels] = useState(false);

  const [llmProvider, setLlmProvider] = useState("openai");
  const [llmKey, setLlmKey] = useState("");
  const [simulatorModel, setSimulatorModel] = useState("gpt-4o-mini");
  const [judgeModel, setJudgeModel] = useState("gpt-4o-mini");
  const [stt, setStt] = useState("pyai");
  const [tts, setTts] = useState("pyai");
  const [voice, setVoice] = useState("alloy");
  const [sttKey, setSttKey] = useState("");
  const [ttsKey, setTtsKey] = useState("");

  const [platform, setPlatform] = useState("retell");
  const [agentId, setAgentId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [roomUrl, setRoomUrl] = useState("");

  const [purpose, setPurpose] = useState("");
  const [categories, setCategories] = useState<string[]>([
    "emotional",
    "compliance",
    "task",
  ]);
  const [perCat, setPerCat] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectedName, setConnectedName] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([client.onboardStatus(), client.providers()])
      .then(([s, providers]) => {
        setStatus(s);
        setCatalog(s.providers || providers);
        // Adding another agent: only need platform + new agent id — don't reuse prior id.
        if (addAgentMode) {
          setPlatform(s.platform || "retell");
          setAgentId("");
          setPurpose("");
        } else {
          if (s.platform) setPlatform(s.platform);
          if (s.agent_id) setAgentId(s.agent_id);
          if (s.purpose) setPurpose(s.purpose);
          if (s.categories?.length) setCategories(s.categories);
          if (s.completed || s.platform) {
            setConnectedName(s.agent_name || s.agent_id || null);
          }
          if (s.platform && !s.completed) setStep(2);
        }
        const c = s.providers || providers;
        const llm = s.caller?.llm_provider || c.defaults.llm;
        setLlmProvider(llm);
        setSimulatorModel(
          s.caller?.simulator_model ||
            c.llm.find((p) => p.id === llm)?.default_model ||
            "gpt-4o-mini",
        );
        setJudgeModel(
          s.caller?.judge_model ||
            c.llm.find((p) => p.id === llm)?.default_model ||
            "gpt-4o-mini",
        );
        setStt(s.caller?.stt || c.defaults.stt);
        setTts(s.caller?.tts || c.defaults.tts);
        setVoice(s.caller?.voice || c.defaults.voice);
      })
      .catch((e: Error) => setError(e.message));
  }, [addAgentMode]);

  const categoriesCatalog: Category[] = status?.categories_catalog || [];
  const platformNeedsKey = platform !== "custom";
  const platformKeyEnv =
    platform === "livekit" ? "LIVEKIT_API_KEY" : `${platform.toUpperCase()}_API_KEY`;
  const platformKeyAlreadySet = Boolean(status?.keys?.[platformKeyEnv]);
  const showPlatformKey = platformNeedsKey && !platformKeyAlreadySet;
  const showLivekitSecret =
    platform === "livekit" &&
    !status?.keys?.LIVEKIT_TOKEN &&
    !status?.keys?.LIVEKIT_API_SECRET;
  const showRoomUrl = platform === "livekit";

  const llmInfo = catalog?.llm.find((p) => p.id === llmProvider);
  const sttInfo = catalog?.stt.find((p) => p.id === stt);
  const ttsInfo = catalog?.tts.find((p) => p.id === tts);

  const needSttKey = sttInfo && sttInfo.env !== llmInfo?.env;
  const needTtsKey =
    ttsInfo && ttsInfo.env !== llmInfo?.env && ttsInfo.env !== sttInfo?.env;

  // Test-agent stack is global; only configure on first run.
  const showTestAgent = !addAgentMode && !status?.caller_configured;

  const canContinue = useMemo(() => {
    if (platform !== "custom" && !agentId.trim()) return false;
    if (showPlatformKey && !apiKey.trim()) return false;
    if (showLivekitSecret && !apiSecret.trim() && !status?.keys?.LIVEKIT_TOKEN) return false;
    if (showRoomUrl && !roomUrl.trim()) return false;
    return true;
  }, [
    platform,
    agentId,
    showPlatformKey,
    apiKey,
    showLivekitSecret,
    apiSecret,
    status?.keys?.LIVEKIT_TOKEN,
    showRoomUrl,
    roomUrl,
  ]);

  function onLlmChange(next: string) {
    setLlmProvider(next);
    const def = catalog?.llm.find((p) => p.id === next)?.default_model;
    if (def) {
      setSimulatorModel(def);
      setJudgeModel(def);
    }
  }

  async function continueToSuite() {
    setBusy(true);
    setError(null);
    try {
      if (showTestAgent) {
        await client.configureCaller({
          llm_provider: llmProvider,
          llm_api_key: llmKey.trim() || null,
          simulator_model: simulatorModel.trim() || "gpt-4o-mini",
          judge_model: judgeModel.trim() || "gpt-4o-mini",
          stt,
          tts,
          voice: voice.trim() || "alloy",
          stt_api_key: needSttKey ? sttKey.trim() || null : null,
          tts_api_key: needTtsKey ? ttsKey.trim() || null : null,
          speech_api_key: null,
        });
      }

      const res = await client.connect({
        platform,
        agent_id: agentId.trim() || null,
        api_key: showPlatformKey && apiKey.trim() ? apiKey.trim() : null,
        api_secret:
          platform === "livekit" && apiSecret.trim() ? apiSecret.trim() : null,
        room_url: showRoomUrl && roomUrl.trim() ? roomUrl.trim() : null,
      });

      setLlmKey("");
      setSttKey("");
      setTtsKey("");
      setApiKey("");
      setApiSecret("");
      setApiKey("");
      setConnectedName(res.agent_name || res.agent_id || platform);
      setStatus(await client.onboardStatus());
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleCat(id: string) {
    setCategories((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id],
    );
  }

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const res = await client.generate({
        purpose,
        categories,
        tests_per_category: perCat,
      });
      setStatus(await client.onboardStatus());
      navigate(`/suites/${res.suite_name}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {addAgentMode ? "Add agent" : "Welcome"}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {addAgentMode
            ? "Pick the provider and agent id. Existing API keys in local .env are reused."
            : "Connect your live agent and configure wiretap's test agent (LLM + speech). Keys stay in local .env only."}
        </p>
      </div>

      <div className="flex gap-2 text-xs">
        <Badge variant={step === 1 ? "default" : "muted"}>
          1 · {addAgentMode ? "Agent" : "Connect"}
        </Badge>
        <Badge variant={step === 2 ? "default" : "muted"}>2 · Tests</Badge>
      </div>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-fail">
          {error}
        </p>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Your Agent</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="block space-y-1 text-sm">
                <span className="text-muted-foreground">Platform</span>
                <select
                  className="h-9 w-full rounded-md border border-border bg-card px-3"
                  value={platform}
                  onChange={(e) => {
                    setPlatform(e.target.value);
                    setApiKey("");
                    setApiSecret("");
                  }}
                >
                  <option value="retell">Retell</option>
                  <option value="vapi">Vapi</option>
                  <option value="elevenlabs">ElevenLabs Agents</option>
                  <option value="livekit">LiveKit Agents</option>
                  <option value="synthflow">Synthflow</option>
                  <option value="bolna">Bolna (import only)</option>
                  <option value="custom">Custom (text stub)</option>
                </select>
              </label>
              {showRoomUrl ? (
                <label className="block space-y-1 text-sm">
                  <span className="text-muted-foreground">LiveKit URL (wss://…)</span>
                  <input
                    className="h-9 w-full rounded-md border border-border bg-card px-3"
                    value={roomUrl}
                    onChange={(e) => setRoomUrl(e.target.value)}
                    placeholder="wss://your-project.livekit.cloud"
                    autoComplete="off"
                  />
                </label>
              ) : null}
              {platformNeedsKey ? (
                <>
                  {showPlatformKey ? (
                    <label className="block space-y-1 text-sm">
                      <span className="text-muted-foreground">
                        {platformKeyEnv}
                      </span>
                      <input
                        type="password"
                        autoComplete="off"
                        className="h-9 w-full rounded-md border border-border bg-card px-3"
                        placeholder="API key"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                      />
                    </label>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Using existing {platformKeyEnv} from .env
                    </p>
                  )}
                  {showLivekitSecret ? (
                    <label className="block space-y-1 text-sm">
                      <span className="text-muted-foreground">LIVEKIT_API_SECRET</span>
                      <input
                        type="password"
                        autoComplete="off"
                        className="h-9 w-full rounded-md border border-border bg-card px-3"
                        placeholder="API secret"
                        value={apiSecret}
                        onChange={(e) => setApiSecret(e.target.value)}
                      />
                    </label>
                  ) : null}
                  <label className="block space-y-1 text-sm">
                    <span className="text-muted-foreground">
                      {platform === "livekit"
                        ? "Room name"
                        : platform === "synthflow"
                          ? "Model / assistant ID"
                          : "Agent ID"}
                    </span>
                    <input
                      className="h-9 w-full rounded-md border border-border bg-card px-3 font-mono text-sm"
                      value={agentId}
                      onChange={(e) => setAgentId(e.target.value)}
                      placeholder={
                        platform === "livekit" ? "my-agent-room" : "agent_xxx"
                      }
                    />
                  </label>
                  {platform === "bolna" ? (
                    <p className="text-xs text-muted-foreground">
                      Bolna import drafts a suite; live phone dial is not wired yet.
                    </p>
                  ) : null}
                  {platform === "synthflow" ? (
                    <p className="text-xs text-muted-foreground">
                      Live dial also needs SYNTHFLOW_FROM_NUMBER / SYNTHFLOW_TO_NUMBER
                      in .env.
                    </p>
                  ) : null}
                </>
              ) : (
                <label className="block space-y-1 text-sm">
                  <span className="text-muted-foreground">Name (optional)</span>
                  <input
                    className="h-9 w-full rounded-md border border-border bg-card px-3"
                    value={agentId}
                    onChange={(e) => setAgentId(e.target.value)}
                    placeholder="my-agent"
                  />
                </label>
              )}
            </CardContent>
          </Card>

          {showTestAgent && (
            <Card>
              <CardHeader>
                <CardTitle>Test Agent</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Wiretap&apos;s test agent that dials your live agent — LLM via LiteLLM;
                  STT/TTS via speech providers (pyai is speech-only and listed first).
                </p>

                <label className="block space-y-1 text-sm">
                  <span className="text-muted-foreground">LLM</span>
                  <select
                    className="h-9 w-full rounded-md border border-border bg-card px-3"
                    value={llmProvider}
                    onChange={(e) => onLlmChange(e.target.value)}
                  >
                    {(catalog?.llm || [{ id: "openai", label: "OpenAI" }]).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block space-y-1 text-sm">
                  <span className="text-muted-foreground">{envLabel(llmInfo)}</span>
                  <input
                    type="password"
                    autoComplete="off"
                    className="h-9 w-full rounded-md border border-border bg-card px-3"
                    placeholder={
                      llmInfo && status?.keys?.[llmInfo.env] ? "•••• set locally" : "API key"
                    }
                    value={llmKey}
                    onChange={(e) => setLlmKey(e.target.value)}
                  />
                </label>

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block space-y-1 text-sm">
                    <span className="text-muted-foreground">STT</span>
                    <select
                      className="h-9 w-full rounded-md border border-border bg-card px-3"
                      value={stt}
                      onChange={(e) => setStt(e.target.value)}
                    >
                      {(catalog?.stt || [{ id: "pyai", label: "PyAI" }]).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block space-y-1 text-sm">
                    <span className="text-muted-foreground">TTS</span>
                    <select
                      className="h-9 w-full rounded-md border border-border bg-card px-3"
                      value={tts}
                      onChange={(e) => setTts(e.target.value)}
                    >
                      {(catalog?.tts || [{ id: "pyai", label: "PyAI" }]).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {needSttKey && (
                  <label className="block space-y-1 text-sm">
                    <span className="text-muted-foreground">
                      STT · {envLabel(sttInfo)}
                    </span>
                    <input
                      type="password"
                      autoComplete="off"
                      className="h-9 w-full rounded-md border border-border bg-card px-3"
                      placeholder={
                        sttInfo && status?.keys?.[sttInfo.env]
                          ? "•••• set locally"
                          : "API key"
                      }
                      value={sttKey}
                      onChange={(e) => setSttKey(e.target.value)}
                    />
                  </label>
                )}
                {needTtsKey && (
                  <label className="block space-y-1 text-sm">
                    <span className="text-muted-foreground">
                      TTS · {envLabel(ttsInfo)}
                    </span>
                    <input
                      type="password"
                      autoComplete="off"
                      className="h-9 w-full rounded-md border border-border bg-card px-3"
                      placeholder={
                        ttsInfo && status?.keys?.[ttsInfo.env]
                          ? "•••• set locally"
                          : "API key"
                      }
                      value={ttsKey}
                      onChange={(e) => setTtsKey(e.target.value)}
                    />
                  </label>
                )}

                <label className="block space-y-1 text-sm">
                  <span className="text-muted-foreground">TTS Voice</span>
                  <input
                    className="h-9 w-full rounded-md border border-border bg-card px-3"
                    value={voice}
                    onChange={(e) => setVoice(e.target.value)}
                    placeholder="alloy"
                  />
                </label>

                <button
                  type="button"
                  className="text-xs text-muted-foreground underline-offset-2 hover:underline"
                  onClick={() => setShowModels((v) => !v)}
                >
                  {showModels ? "Hide models" : "Test Agent / Judge Models"}
                </button>
                {showModels && (
                  <div className="grid gap-3 sm:grid-cols-2 border-t border-border pt-4">
                    <label className="block space-y-1 text-sm">
                      <span className="text-muted-foreground">Test Agent Model</span>
                      <input
                        className="h-9 w-full rounded-md border border-border bg-card px-3 font-mono text-sm"
                        value={simulatorModel}
                        onChange={(e) => setSimulatorModel(e.target.value)}
                      />
                    </label>
                    <label className="block space-y-1 text-sm">
                      <span className="text-muted-foreground">Judge Model</span>
                      <input
                        className="h-9 w-full rounded-md border border-border bg-card px-3 font-mono text-sm"
                        value={judgeModel}
                        onChange={(e) => setJudgeModel(e.target.value)}
                      />
                    </label>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {addAgentMode && status?.caller_configured && (
            <p className="text-xs text-muted-foreground">
              Test agent already configured ({status.caller?.llm_provider} / STT{" "}
              {status.caller?.stt} / TTS {status.caller?.tts}). Not asked again.
            </p>
          )}

          <Button onClick={continueToSuite} disabled={busy || !canContinue}>
            {busy ? "Connecting…" : "Continue"}
          </Button>
        </div>
      )}

      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>What To Test</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {connectedName && (
              <p className="text-sm text-muted-foreground">
                Agent: <span className="text-foreground">{connectedName}</span>
              </p>
            )}
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Purpose (optional)</span>
              <textarea
                className="min-h-20 w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="e.g. cancellation and refund flows"
              />
            </label>
            <div className="space-y-2">
              <div className="text-sm text-muted-foreground">Categories</div>
              {categoriesCatalog.map((c) => (
                <label
                  key={c.id}
                  className="flex cursor-pointer items-start gap-3 rounded-md border border-border px-3 py-2 text-sm hover:bg-muted/40"
                >
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={categories.includes(c.id)}
                    onChange={() => toggleCat(c.id)}
                  />
                  <span>
                    <span className="font-medium">{c.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {c.description}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <label className="flex items-center gap-2 text-sm">
              Tests per category
              <input
                type="number"
                min={1}
                max={10}
                className="h-9 w-16 rounded-md border border-border bg-card px-2"
                value={perCat}
                onChange={(e) =>
                  setPerCat(Math.min(10, Math.max(1, Number(e.target.value) || 1)))
                }
              />
            </label>
            <p className="text-xs text-muted-foreground">
              About {categories.length * perCat} scenarios
              {status?.caller_configured && status.caller?.llm_provider
                ? ` · Test Agent ${status.caller.llm_provider} / STT ${status.caller.stt} / TTS ${status.caller.tts}`
                : ` · Test Agent ${llmProvider} / STT ${stt} / TTS ${tts}`}
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button onClick={generate} disabled={busy || categories.length === 0}>
                {busy ? "Generating…" : "Generate suite"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
