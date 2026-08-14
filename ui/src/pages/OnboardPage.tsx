import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  client,
  type Category,
  type OnboardStatus,
  type ProviderCatalog,
  type ProviderInfo,
} from "@/lib/api";
import { AppSelect } from "@/components/AppSelect";
import { PhoneTestingCard } from "@/components/PhoneTestingCard";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** Mirrors `wiretap init`: simulator → live agent → suite → phone. */
type Step = 1 | 2 | 3 | 4;

const PLATFORMS = [
  { value: "retell", label: "Retell" },
  { value: "vapi", label: "Vapi" },
  { value: "elevenlabs", label: "ElevenLabs Agents" },
  { value: "livekit", label: "LiveKit Agents" },
  { value: "synthflow", label: "Synthflow" },
  { value: "bolna", label: "Bolna (import only)" },
  { value: "custom", label: "Custom (text stub)" },
] as const;

function envLabel(p?: ProviderInfo | null) {
  return p?.env || "API key";
}

function StepRail({
  steps,
  current,
}: {
  steps: { id: Step; label: string; detail: string }[];
  current: Step;
}) {
  return (
    <ol className="flex flex-col gap-0 sm:flex-row sm:flex-wrap sm:items-center sm:gap-1">
      {steps.map((s, i) => {
        const done = s.id < current;
        const active = s.id === current;
        return (
          <li key={s.id} className="flex items-center gap-1">
            <div
              className={cn(
                "flex items-center gap-2 rounded-full px-2.5 py-1 text-[12.5px]",
                active && "bg-[var(--wt-section)] font-medium text-foreground",
                done && "text-muted-foreground",
                !active && !done && "text-[var(--wt-text-muted)]",
              )}
            >
              <span
                className={cn(
                  "inline-flex size-5 items-center justify-center rounded-full font-mono text-[11px]",
                  active && "bg-primary text-primary-foreground",
                  done && "bg-[var(--wt-green-100)] text-[var(--wt-green-700)]",
                  !active && !done && "bg-muted text-muted-foreground",
                )}
              >
                {done ? "✓" : s.id}
              </span>
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {i < steps.length - 1 ? (
              <span className="mx-0.5 hidden text-[var(--wt-text-muted)] sm:inline">
                ·
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function Section({
  kicker,
  title,
  description,
  children,
}: {
  kicker: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2.5">
      <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
        {kicker}
      </div>
      <div className="rounded-[14px] border border-border bg-card px-[22px] pt-[22px] pb-5">
        <h2 className="mb-1 text-[15px] font-semibold text-foreground">{title}</h2>
        <p className="mb-[18px] max-w-2xl text-[13px] leading-relaxed text-muted-foreground text-pretty">
          {description}
        </p>
        {children}
      </div>
    </section>
  );
}

function FieldRow({
  label,
  subLabel,
  first,
  children,
}: {
  label: string;
  subLabel: string;
  first?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 items-start gap-x-5 gap-y-3 py-3.5 sm:grid-cols-[200px_1fr]",
        !first && "border-t border-border",
      )}
    >
      <div className="min-w-0 pt-2">
        <div className="mb-0.5 text-[13.5px] font-medium text-foreground">
          {label}
        </div>
        <div className="font-mono text-[11.5px] text-[var(--wt-text-muted)]">
          {subLabel}
        </div>
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function OnboardPage({
  addAgentMode: addAgentModeProp,
  compact = false,
  onFinished,
}: {
  addAgentMode?: boolean;
  /** Tighter typography/spacing when embedded in a modal. */
  compact?: boolean;
  onFinished?: (result: { suiteName: string | null }) => void;
} = {}) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const addAgentMode =
    addAgentModeProp ?? params.get("again") === "1";

  const [step, setStep] = useState<Step>(addAgentMode ? 2 : 1);
  const [status, setStatus] = useState<OnboardStatus | null>(null);
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);

  const [llmProvider, setLlmProvider] = useState("openai");
  const [llmKey, setLlmKey] = useState("");
  const [simulatorModel, setSimulatorModel] = useState("gpt-4o-mini");
  const [judgeModel, setJudgeModel] = useState("gpt-4o-mini");
  const [liveModels, setLiveModels] = useState<string[] | null>(null);
  const [stt, setStt] = useState("pyai");
  const [tts, setTts] = useState("pyai");
  const [voice, setVoice] = useState("alloy");
  const [liveVoices, setLiveVoices] = useState<
    { id: string; label: string }[] | null
  >(null);
  const [sttKey, setSttKey] = useState("");
  const [ttsKey, setTtsKey] = useState("");
  const [showAdvancedModels, setShowAdvancedModels] = useState(false);

  const [platform, setPlatform] = useState("retell");
  const [agentId, setAgentId] = useState("");
  const [remoteAgents, setRemoteAgents] = useState<
    { id: string; name: string; label: string }[] | null
  >(null);
  const [agentsLoading, setAgentsLoading] = useState(false);
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
  const [generatedSuite, setGeneratedSuite] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([client.onboardStatus(), client.providers()])
      .then(([s, providers]) => {
        if (cancelled) return;
        setStatus(s);
        const c = s.providers || providers;
        setCatalog(c);

        if (addAgentMode) {
          setPlatform(s.platform || "retell");
          setAgentId("");
          setPurpose("");
          setStep(2);
        } else {
          if (s.platform) setPlatform(s.platform);
          if (s.agent_id) setAgentId(s.agent_id);
          if (s.purpose) setPurpose(s.purpose);
          if (s.categories?.length) setCategories(s.categories);
          if (s.completed || s.platform) {
            setConnectedName(s.agent_name || s.agent_id || null);
          }
          // Resume where CLI-equivalent progress left off.
          if (s.caller_configured && !s.platform) setStep(2);
          else if (s.platform && !s.completed) setStep(3);
          else if (!s.caller_configured) setStep(1);
        }

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
        const ttsId = s.caller?.tts || c.defaults.tts;
        const ttsProv = c.tts.find((p) => p.id === ttsId);
        setVoice(
          s.caller?.voice ||
            ttsProv?.default_voice ||
            c.defaults.voice ||
            "alloy",
        );

        void client
          .llmModels(llm)
          .then((res) => setLiveModels(res.models))
          .catch(() => setLiveModels(null));
        void client
          .ttsVoices(ttsId)
          .then((res) => setLiveVoices(res.voices))
          .catch(() => setLiveVoices(null));
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });

    const onFocus = () => {
      void client.onboardStatus().then((s) => {
        if (!cancelled) setStatus(s);
      });
    };
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, [addAgentMode]);

  const categoriesCatalog: Category[] =
    status?.categories_catalog?.length
      ? status.categories_catalog
      : [];
  const keys = status?.keys ?? {};
  const platformNeedsKey = platform !== "custom";
  const platformKeyEnv =
    platform === "livekit"
      ? "LIVEKIT_API_KEY"
      : `${platform.toUpperCase()}_API_KEY`;
  const platformKeyAlreadySet = Boolean(keys[platformKeyEnv]);
  const showPlatformKey = platformNeedsKey && !platformKeyAlreadySet;
  const showLivekitSecret =
    platform === "livekit" && !keys.LIVEKIT_TOKEN && !keys.LIVEKIT_API_SECRET;
  const showRoomUrl = platform === "livekit";
  const supportsLiveAgents = ["retell", "vapi", "elevenlabs"].includes(platform);

  const llmInfo = catalog?.llm.find((p) => p.id === llmProvider) || null;
  const sttInfo = catalog?.stt.find((p) => p.id === stt) || null;
  const ttsInfo = catalog?.tts.find((p) => p.id === tts) || null;
  const modelChoices = liveModels?.length
    ? liveModels
    : llmInfo?.models?.length
      ? llmInfo.models
      : ([llmInfo?.default_model || "gpt-4o-mini"].filter(Boolean) as string[]);
  const voiceChoices =
    liveVoices ?? (ttsInfo?.voices?.length ? ttsInfo.voices : []);

  const needSttKey = Boolean(sttInfo && sttInfo.env !== llmInfo?.env);
  const needTtsKey = Boolean(
    ttsInfo && ttsInfo.env !== llmInfo?.env && ttsInfo.env !== sttInfo?.env,
  );

  const showSimulator = !addAgentMode && !status?.caller_configured;

  const railSteps = useMemo(() => {
    if (addAgentMode) {
      return [
        { id: 2 as Step, label: "Live agent", detail: "Connect" },
        { id: 3 as Step, label: "Suite", detail: "Optional" },
        { id: 4 as Step, label: "Phone", detail: "Optional" },
      ];
    }
    return [
      { id: 1 as Step, label: "Simulator", detail: "Tester agent" },
      { id: 2 as Step, label: "Live agent", detail: "Connect" },
      { id: 3 as Step, label: "Suite", detail: "Generate" },
      { id: 4 as Step, label: "Phone", detail: "Optional" },
    ];
  }, [addAgentMode]);

  async function refreshModels(provider: string, keyHint?: string) {
    try {
      const res = await client.llmModels(provider, keyHint || llmKey || null);
      setLiveModels(res.models);
      if (res.default_model) {
        setSimulatorModel((prev) =>
          res.models.includes(prev) ? prev : res.default_model,
        );
        setJudgeModel((prev) =>
          res.models.includes(prev) ? prev : res.default_model,
        );
      }
    } catch {
      setLiveModels(null);
    }
  }

  async function refreshVoices(provider: string, keyHint?: string) {
    try {
      const res = await client.ttsVoices(provider, keyHint || ttsKey || null);
      setLiveVoices(res.voices);
      if (res.default_voice) {
        setVoice((prev) =>
          res.voices.some((v) => v.id === prev) ? prev : res.default_voice,
        );
      }
    } catch {
      setLiveVoices(null);
    }
  }

  async function refreshAgents(nextPlatform: string, keyHint?: string) {
    if (!["retell", "vapi", "elevenlabs"].includes(nextPlatform)) {
      setRemoteAgents(null);
      setAgentsLoading(false);
      return;
    }
    setAgentsLoading(true);
    setRemoteAgents(null);
    try {
      const res = await client.platformAgents(
        nextPlatform,
        keyHint || apiKey || null,
      );
      if (res.source === "live" && res.agents.length) {
        setRemoteAgents(res.agents);
        setAgentId((prev) => prev || res.agents[0].id);
      } else {
        setRemoteAgents(null);
      }
    } catch {
      setRemoteAgents(null);
    } finally {
      setAgentsLoading(false);
    }
  }

  useEffect(() => {
    if (step !== 2) return;
    void refreshAgents(platform);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, platform, status?.keys]);

  function onLlmChange(next: string) {
    setLlmProvider(next);
    setLiveModels(null);
    const info = catalog?.llm.find((p) => p.id === next);
    const def = info?.default_model || info?.models?.[0];
    if (def) {
      setSimulatorModel(def);
      setJudgeModel(def);
    }
    void refreshModels(next);
  }

  function onTtsChange(next: string) {
    setTts(next);
    setLiveVoices(null);
    const info = catalog?.tts.find((p) => p.id === next);
    const def =
      info?.default_voice || info?.voices?.[0]?.id || catalog?.defaults.voice;
    if (def) setVoice(def);
    void refreshVoices(next);
  }

  const canSaveSimulator = Boolean(llmProvider && stt && tts);
  const canConnect = useMemo(() => {
    if (platform !== "custom" && !agentId.trim()) return false;
    if (showPlatformKey && !apiKey.trim()) return false;
    if (showLivekitSecret && !apiSecret.trim() && !keys.LIVEKIT_TOKEN) {
      return false;
    }
    if (showRoomUrl && !roomUrl.trim()) return false;
    if (agentsLoading) return false;
    return true;
  }, [
    platform,
    agentId,
    showPlatformKey,
    apiKey,
    showLivekitSecret,
    apiSecret,
    keys.LIVEKIT_TOKEN,
    showRoomUrl,
    roomUrl,
    agentsLoading,
  ]);

  async function saveSimulator() {
    setBusy(true);
    setError(null);
    try {
      await client.configureCaller({
        llm_provider: llmProvider,
        llm_api_key: llmKey.trim() || null,
        simulator_model: simulatorModel.trim() || "gpt-4o-mini",
        judge_model: judgeModel.trim() || "gpt-4o-mini",
        stt,
        tts,
        voice:
          voice.trim() ||
          ttsInfo?.default_voice ||
          catalog?.defaults.voice ||
          "alloy",
        stt_api_key: needSttKey ? sttKey.trim() || null : null,
        tts_api_key: needTtsKey ? ttsKey.trim() || null : null,
        speech_api_key: null,
      });
      setLlmKey("");
      setSttKey("");
      setTtsKey("");
      setStatus(await client.onboardStatus());
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function connectLive() {
    setBusy(true);
    setError(null);
    try {
      const res = await client.connect({
        platform,
        agent_id: agentId.trim() || null,
        api_key: showPlatformKey && apiKey.trim() ? apiKey.trim() : null,
        api_secret:
          platform === "livekit" && apiSecret.trim() ? apiSecret.trim() : null,
        room_url: showRoomUrl && roomUrl.trim() ? roomUrl.trim() : null,
      });
      setApiKey("");
      setApiSecret("");
      setConnectedName(res.agent_name || res.agent_id || platform);
      if (res.suite_name) setGeneratedSuite(res.suite_name);
      setStatus(await client.onboardStatus());
      setStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function generateSuite() {
    setBusy(true);
    setError(null);
    try {
      const res = await client.generate({
        purpose,
        categories,
        tests_per_category: perCat,
      });
      setGeneratedSuite(res.suite_name);
      setStatus(await client.onboardStatus());
      setStep(4);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function finish() {
    const suiteName = generatedSuite;
    if (onFinished) {
      onFinished({ suiteName });
      return;
    }
    navigate(suiteName ? `/suites/${encodeURIComponent(suiteName)}` : "/suites");
  }

  function toggleCat(id: string) {
    setCategories((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id],
    );
  }

  // Skip simulator if already configured.
  useEffect(() => {
    if (addAgentMode || showSimulator) return;
    if (step === 1 && status?.caller_configured) setStep(2);
  }, [addAgentMode, showSimulator, step, status?.caller_configured]);

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col",
        compact ? "max-w-none gap-5 pb-2" : "max-w-[960px] gap-7 pb-8",
      )}
    >
      <header
        className={cn(
          "flex flex-col gap-4 border-b border-border",
          compact ? "pb-4" : "pb-5",
        )}
      >
        <div>
          <h1
            className={cn(
              "font-semibold tracking-[-0.005em] text-foreground",
              compact ? "text-[18px]" : "text-[22px]",
            )}
          >
            Welcome
          </h1>
          <p className="mt-1 max-w-xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
            {addAgentMode
              ? "Connect another live agent. Existing simulator keys are reused."
              : "Same path as wiretap init — simulator, live agent, suite, then optional phone. Keys stay in the local secret store."}
          </p>
        </div>
        <StepRail steps={railSteps} current={step} />
      </header>

      {error && <p className="text-sm text-fail">{error}</p>}

      {/* 1 · Simulator */}
      {step === 1 && !addAgentMode && (
        <Section
          kicker="Step 1 · Simulator"
          title="Tester agent"
          description="The synthetic caller that dials your live agent. Configure LLM and speech once — Settings can change this later."
        >
          {!showSimulator ? (
            <div className="flex flex-col gap-4">
              <p className="text-[13.5px] text-muted-foreground">
                Simulator already configured
                {status?.caller?.llm_provider
                  ? ` · ${status.caller.llm_provider} / ${status.caller.stt} / ${status.caller.tts}`
                  : ""}
                .
              </p>
              <div className="flex justify-end gap-2">
                <Button onClick={() => setStep(2)}>Continue</Button>
              </div>
            </div>
          ) : (
            <>
              <FieldRow label="Speech-to-text" subLabel="transcribes the call" first>
                <div className="grid gap-2.5 sm:grid-cols-[minmax(140px,180px)_1fr]">
                  <AppSelect
                    value={stt}
                    onValueChange={setStt}
                    options={(catalog?.stt || [{ id: "pyai", label: "PyAI" }]).map(
                      (p) => ({ value: p.id, label: p.label }),
                    )}
                  />
                  {needSttKey ? (
                    <Input
                      type="password"
                      autoComplete="off"
                      className="h-10 rounded-[10px] font-mono text-sm"
                      placeholder={
                        sttInfo && keys[sttInfo.env]
                          ? "•••• set locally"
                          : envLabel(sttInfo)
                      }
                      value={sttKey}
                      onChange={(e) => setSttKey(e.target.value)}
                    />
                  ) : (
                    <div className="flex h-10 items-center rounded-[10px] border border-border bg-[var(--wt-section)] px-3.5 font-mono text-[12.5px] text-muted-foreground">
                      Uses {sttInfo?.env || "LLM key"}
                    </div>
                  )}
                </div>
              </FieldRow>

              <FieldRow label="Text-to-speech" subLabel="voices the tester">
                <div className="grid gap-2.5 sm:grid-cols-[minmax(140px,180px)_1fr]">
                  <AppSelect
                    value={tts}
                    onValueChange={onTtsChange}
                    options={(catalog?.tts || [{ id: "pyai", label: "PyAI" }]).map(
                      (p) => ({ value: p.id, label: p.label }),
                    )}
                  />
                  {needTtsKey ? (
                    <Input
                      type="password"
                      autoComplete="off"
                      className="h-10 rounded-[10px] font-mono text-sm"
                      placeholder={
                        ttsInfo && keys[ttsInfo.env]
                          ? "•••• set locally"
                          : envLabel(ttsInfo)
                      }
                      value={ttsKey}
                      onChange={(e) => setTtsKey(e.target.value)}
                    />
                  ) : (
                    <div className="flex h-10 items-center rounded-[10px] border border-border bg-[var(--wt-section)] px-3.5 font-mono text-[12.5px] text-muted-foreground">
                      Uses {ttsInfo?.env || "shared key"}
                    </div>
                  )}
                </div>
              </FieldRow>

              <FieldRow label="LLM" subLabel="drives tester replies">
                <div className="grid gap-2.5 sm:grid-cols-[minmax(140px,180px)_1fr]">
                  <AppSelect
                    value={llmProvider}
                    onValueChange={onLlmChange}
                    options={(
                      catalog?.llm || [{ id: "openai", label: "OpenAI" }]
                    ).map((p) => ({ value: p.id, label: p.label }))}
                  />
                  <Input
                    type="password"
                    autoComplete="off"
                    className="h-10 rounded-[10px] font-mono text-sm"
                    placeholder={
                      llmInfo && keys[llmInfo.env]
                        ? "•••• set locally"
                        : envLabel(llmInfo)
                    }
                    value={llmKey}
                    onChange={(e) => setLlmKey(e.target.value)}
                    onBlur={() => {
                      if (llmKey.trim()) void refreshModels(llmProvider, llmKey);
                    }}
                  />
                </div>
              </FieldRow>

              <FieldRow label="Models" subLabel="simulator · judge">
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    className="w-fit text-[12.5px] font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                    onClick={() => setShowAdvancedModels((v) => !v)}
                  >
                    {showAdvancedModels ? "Hide models" : "Show models"}
                  </button>
                  {showAdvancedModels ? (
                    <div className="grid gap-2.5 sm:grid-cols-2">
                      <AppSelect
                        mono
                        value={
                          modelChoices.includes(simulatorModel)
                            ? simulatorModel
                            : modelChoices[0] || simulatorModel
                        }
                        onValueChange={setSimulatorModel}
                        options={modelChoices.map((m) => ({
                          value: m,
                          label: m,
                        }))}
                      />
                      <AppSelect
                        mono
                        value={
                          modelChoices.includes(judgeModel)
                            ? judgeModel
                            : modelChoices[0] || judgeModel
                        }
                        onValueChange={setJudgeModel}
                        options={modelChoices.map((m) => ({
                          value: m,
                          label: m,
                        }))}
                      />
                    </div>
                  ) : null}
                  {voiceChoices.length > 0 ? (
                    <div className="max-w-xs">
                      <Label className="mb-1.5 block text-[12.5px] text-muted-foreground">
                        Voice
                      </Label>
                      <AppSelect
                        value={voice || voiceChoices[0]?.id}
                        onValueChange={setVoice}
                        options={voiceChoices.map((v) => ({
                          value: v.id,
                          label: v.label || v.id,
                        }))}
                      />
                    </div>
                  ) : null}
                </div>
              </FieldRow>

              <div className="mt-5 flex justify-end">
                <Button
                  onClick={() => void saveSimulator()}
                  disabled={busy || !canSaveSimulator}
                >
                  {busy ? "Saving…" : "Continue"}
                </Button>
              </div>
            </>
          )}
        </Section>
      )}

      {/* 2 · Live agent */}
      {step === 2 && (
        <Section
          kicker="Step 2 · Live agent"
          title="Connect production agent"
          description="Import the voice agent you want to dial during simulate. Platform keys are write-only."
        >
          <FieldRow label="Platform" subLabel="provider" first>
            <AppSelect
              value={platform}
              onValueChange={(next) => {
                setPlatform(next);
                setApiKey("");
                setApiSecret("");
                setRemoteAgents(null);
                setAgentId("");
                void refreshAgents(next);
              }}
              options={[...PLATFORMS]}
            />
          </FieldRow>

          {showRoomUrl ? (
            <FieldRow label="LiveKit URL" subLabel="wss://…">
              <Input
                className="h-10 rounded-[10px]"
                value={roomUrl}
                onChange={(e) => setRoomUrl(e.target.value)}
                placeholder="wss://your-project.livekit.cloud"
                autoComplete="off"
              />
            </FieldRow>
          ) : null}

          {platformNeedsKey ? (
            <>
              <FieldRow label="API key" subLabel={platformKeyEnv}>
                {showPlatformKey ? (
                  <Input
                    type="password"
                    autoComplete="off"
                    className="h-10 rounded-[10px] font-mono text-sm"
                    placeholder="API key"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    onBlur={() => {
                      if (apiKey.trim()) void refreshAgents(platform, apiKey);
                    }}
                  />
                ) : (
                  <div className="flex h-10 items-center rounded-[10px] border border-border bg-[var(--wt-section)] px-3.5 font-mono text-[12.5px] text-muted-foreground">
                    Using existing {platformKeyEnv}
                  </div>
                )}
              </FieldRow>

              {showLivekitSecret ? (
                <FieldRow label="API secret" subLabel="LIVEKIT_API_SECRET">
                  <Input
                    type="password"
                    autoComplete="off"
                    className="h-10 rounded-[10px] font-mono text-sm"
                    placeholder="API secret"
                    value={apiSecret}
                    onChange={(e) => setApiSecret(e.target.value)}
                  />
                </FieldRow>
              ) : null}

              <FieldRow
                label={
                  platform === "livekit"
                    ? "Room"
                    : platform === "synthflow"
                      ? "Model ID"
                      : "Agent"
                }
                subLabel="target"
              >
                {agentsLoading && supportsLiveAgents ? (
                  <AppSelect
                    disabled
                    value="__loading__"
                    onValueChange={() => {}}
                    options={[
                      {
                        value: "__loading__",
                        label: "Loading…",
                        disabled: true,
                      },
                    ]}
                  />
                ) : remoteAgents && remoteAgents.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    <AppSelect
                      value={
                        remoteAgents.some((a) => a.id === agentId)
                          ? agentId
                          : "__custom__"
                      }
                      onValueChange={(v) => {
                        if (v === "__custom__") {
                          setAgentId("");
                          return;
                        }
                        setAgentId(v);
                      }}
                      options={[
                        ...remoteAgents.map((a) => ({
                          value: a.id,
                          label: a.name,
                        })),
                        { value: "__custom__", label: "Paste custom id…" },
                      ]}
                    />
                    {(!remoteAgents.some((a) => a.id === agentId) ||
                      !agentId) && (
                      <Input
                        className="h-10 rounded-[10px] text-sm"
                        value={agentId}
                        onChange={(e) => setAgentId(e.target.value)}
                        placeholder="agent_xxx"
                      />
                    )}
                  </div>
                ) : (
                  <Input
                    className="h-10 rounded-[10px] text-sm"
                    value={agentId}
                    onChange={(e) => setAgentId(e.target.value)}
                    placeholder={
                      platform === "livekit" ? "my-agent-room" : "agent_xxx"
                    }
                  />
                )}
              </FieldRow>
            </>
          ) : (
            <FieldRow label="Name" subLabel="optional">
              <Input
                className="h-10 rounded-[10px]"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                placeholder="my-agent"
              />
            </FieldRow>
          )}

          {platform === "bolna" ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Bolna import drafts a suite; live phone dial is not wired yet.
            </p>
          ) : null}

          <div className="mt-5 flex flex-wrap justify-between gap-2">
            {!addAgentMode ? (
              <Button
                variant="outline"
                onClick={() => setStep(1)}
                disabled={busy}
              >
                Back
              </Button>
            ) : (
              <span />
            )}
            <Button
              onClick={() => void connectLive()}
              disabled={busy || !canConnect}
            >
              {busy ? "Connecting…" : "Connect & continue"}
            </Button>
          </div>
        </Section>
      )}

      {/* 3 · Suite */}
      {step === 3 && (
        <Section
          kicker="Step 3 · Test suite"
          title="Generate category tests"
          description={
            connectedName
              ? `Build scenarios for ${connectedName}. You can skip and author cases later from Test Suites.`
              : "Build scenarios for the connected agent. You can skip and author cases later."
          }
        >
          <FieldRow label="Purpose" subLabel="optional" first>
            <Input
              className="h-10 rounded-[10px]"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="e.g. cancellation and refund flows"
            />
          </FieldRow>

          <FieldRow label="Categories" subLabel="eval buckets">
            <div className="max-h-56 overflow-y-auto rounded-[10px] border border-border">
              {(categoriesCatalog.length
                ? categoriesCatalog
                : [
                    {
                      id: "emotional",
                      label: "Emotional",
                      description: "",
                      max_tests: 10,
                    },
                    {
                      id: "compliance",
                      label: "Compliance",
                      description: "",
                      max_tests: 10,
                    },
                    {
                      id: "task",
                      label: "Task",
                      description: "",
                      max_tests: 10,
                    },
                  ]
              ).map((c, i) => (
                <label
                  key={c.id}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 px-3 py-2.5 text-sm hover:bg-[var(--wt-section)]",
                    i > 0 && "border-t border-border",
                  )}
                >
                  <Checkbox
                    checked={categories.includes(c.id)}
                    onCheckedChange={() => toggleCat(c.id)}
                    className="mt-0.5"
                  />
                  <span className="min-w-0">
                    <span className="font-medium text-foreground">{c.label}</span>
                    {c.description ? (
                      <span className="mt-0.5 block text-[12.5px] leading-snug text-muted-foreground">
                        {c.description}
                      </span>
                    ) : null}
                  </span>
                </label>
              ))}
            </div>
          </FieldRow>

          <FieldRow label="Depth" subLabel="per category">
            <div className="flex flex-wrap items-center gap-3">
              <Input
                type="number"
                min={1}
                max={10}
                className="h-10 w-20 rounded-[10px]"
                value={perCat}
                onChange={(e) =>
                  setPerCat(
                    Math.min(10, Math.max(1, Number(e.target.value) || 1)),
                  )
                }
              />
              <span className="text-[12.5px] text-muted-foreground">
                ≈ {categories.length * perCat} scenarios
              </span>
            </div>
          </FieldRow>

          <div className="mt-5 flex flex-wrap justify-between gap-2">
            <Button variant="outline" onClick={() => setStep(2)} disabled={busy}>
              Back
            </Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => setStep(4)}
              >
                Skip for now
              </Button>
              <Button
                onClick={() => void generateSuite()}
                disabled={busy || categories.length === 0}
              >
                {busy ? "Generating…" : "Generate suite"}
              </Button>
            </div>
          </div>
        </Section>
      )}

      {/* 4 · Phone */}
      {step === 4 && (
        <Section
          kicker="Step 4 · Phone · optional"
          title="Phone testing"
          description="Optional Twilio setup for real PSTN runs. Web/WebRTC works without this — you can finish later in Settings."
        >
          {generatedSuite ? (
            <p className="mb-4 text-[13.5px] text-muted-foreground">
              Suite{" "}
              <span className="font-medium text-foreground">{generatedSuite}</span>{" "}
              is ready.
            </p>
          ) : null}
          <PhoneTestingCard />
          <div className="mt-5 flex flex-wrap justify-between gap-2">
            <Button variant="outline" onClick={() => setStep(3)} disabled={busy}>
              Back
            </Button>
            <Button onClick={finish}>
              {generatedSuite ? "Open suite" : "Go to suites"}
            </Button>
          </div>
        </Section>
      )}
    </div>
  );
}
