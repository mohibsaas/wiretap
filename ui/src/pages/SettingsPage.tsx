import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Eye, EyeOff, Minus, Plus, RefreshCw } from "lucide-react";
import { ConnectAgentDialog } from "@/components/ConnectAgentDialog";
import { PhoneTestingCard } from "@/components/PhoneTestingCard";
import { AppSelect } from "@/components/AppSelect";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  client,
  type AgentRow,
  type OnboardStatus,
  type ProviderCatalog,
  type ProviderInfo,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const CONCURRENCY_KEY = "wiretap.defaultConcurrency";

const TARGET_PLATFORMS: { id: string; label: string; env: string }[] = [
  { id: "retell", label: "Retell", env: "RETELL_API_KEY" },
  { id: "vapi", label: "Vapi", env: "VAPI_API_KEY" },
  { id: "elevenlabs", label: "ElevenLabs", env: "ELEVENLABS_API_KEY" },
  { id: "livekit", label: "LiveKit", env: "LIVEKIT_API_KEY" },
  { id: "synthflow", label: "Synthflow", env: "SYNTHFLOW_API_KEY" },
  { id: "bolna", label: "Bolna", env: "BOLNA_API_KEY" },
];

function readConcurrency(): number {
  try {
    const raw = localStorage.getItem(CONCURRENCY_KEY);
    const n = raw ? Number(raw) : 4;
    if (Number.isFinite(n) && n >= 1 && n <= 32) return Math.floor(n);
  } catch {
    /* ignore */
  }
  return 4;
}

function envLabel(info?: ProviderInfo | null): string {
  return info?.env || "API_KEY";
}

export function SettingsPage() {
  const [status, setStatus] = useState<OnboardStatus | null>(null);
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [llm, setLlm] = useState("openai");
  const [stt, setStt] = useState("pyai");
  const [tts, setTts] = useState("pyai");
  const [simulatorModel, setSimulatorModel] = useState("");
  const [judgeModel, setJudgeModel] = useState("");
  const [voice, setVoice] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([]);

  const [llmKey, setLlmKey] = useState("");
  const [sttKey, setSttKey] = useState("");
  const [ttsKey, setTtsKey] = useState("");

  const [concurrency, setConcurrency] = useState(readConcurrency);
  const [connectOpen, setConnectOpen] = useState(false);
  const [connectPlatform, setConnectPlatform] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [s, p, a] = await Promise.all([
      client.onboardStatus(),
      client.providers().catch(() => null),
      client.agents().catch(() => [] as AgentRow[]),
    ]);
    setStatus(s);
    setAgents(a);
    const cat = p || s.providers || null;
    setCatalog(cat);

    const caller = s.caller;
    const defaults = cat?.defaults;
    setLlm(caller?.llm_provider || defaults?.llm || "openai");
    setStt(caller?.stt || defaults?.stt || "pyai");
    setTts(caller?.tts || defaults?.tts || "pyai");
    setSimulatorModel(caller?.simulator_model || "");
    setJudgeModel(caller?.judge_model || "");
    setVoice(caller?.voice || defaults?.voice || "");
  }, []);

  useEffect(() => {
    void refresh().catch((e: Error) => setError(e.message));
  }, [refresh]);

  const llmInfo = useMemo(
    () => catalog?.llm.find((p) => p.id === llm) || null,
    [catalog, llm],
  );
  const sttInfo = useMemo(
    () => catalog?.stt.find((p) => p.id === stt) || null,
    [catalog, stt],
  );
  const ttsInfo = useMemo(
    () => catalog?.tts.find((p) => p.id === tts) || null,
    [catalog, tts],
  );

  const keys = status?.keys ?? {};
  const needSttKey = Boolean(sttInfo && sttInfo.env !== llmInfo?.env);
  const needTtsKey = Boolean(
    ttsInfo && ttsInfo.env !== llmInfo?.env && ttsInfo.env !== sttInfo?.env,
  );

  const modelOptions = useMemo(() => {
    if (models.length) return models;
    if (llmInfo?.models?.length) return llmInfo.models;
    const d = llmInfo?.default_model;
    return d ? [d] : [];
  }, [models, llmInfo]);

  const voiceOptions = useMemo(() => {
    if (voices.length) return voices;
    return ttsInfo?.voices?.length ? ttsInfo.voices : [];
  }, [voices, ttsInfo]);

  async function loadModels(provider: string, keyHint?: string) {
    try {
      const res = await client.llmModels(provider, keyHint || llmKey || null);
      setModels(res.models || []);
      if (res.default_model) {
        setSimulatorModel((prev) => prev || res.default_model);
        setJudgeModel((prev) => prev || res.default_model);
      }
    } catch {
      setModels(llmInfo?.models || []);
    }
  }

  async function loadVoices(provider: string, keyHint?: string) {
    try {
      const res = await client.ttsVoices(provider, keyHint || ttsKey || null);
      setVoices(res.voices || []);
      if (res.default_voice) {
        setVoice((prev) => prev || res.default_voice);
      }
    } catch {
      setVoices(ttsInfo?.voices || []);
    }
  }

  useEffect(() => {
    if (!llm) return;
    void loadModels(llm);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when provider changes
  }, [llm, catalog]);

  useEffect(() => {
    if (!tts) return;
    void loadVoices(tts);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tts, catalog]);

  function onLlmChange(next: string) {
    setLlm(next);
    setLlmKey("");
    const info = catalog?.llm.find((p) => p.id === next);
    const d = info?.default_model || "";
    setSimulatorModel(d);
    setJudgeModel(d);
    setModels(info?.models || []);
  }

  function onTtsChange(next: string) {
    setTts(next);
    setTtsKey("");
    const info = catalog?.tts.find((p) => p.id === next);
    setVoice(info?.default_voice || "");
    setVoices(info?.voices || []);
  }

  function bumpConcurrency(delta: number) {
    setConcurrency((n) => {
      const next = Math.min(32, Math.max(1, n + delta));
      try {
        localStorage.setItem(CONCURRENCY_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  async function saveTester() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await client.configureCaller({
        llm_provider: llm,
        llm_api_key: llmKey.trim() || null,
        simulator_model: simulatorModel || undefined,
        judge_model: judgeModel || undefined,
        stt,
        tts,
        voice: voice || undefined,
        stt_api_key: needSttKey ? sttKey.trim() || null : null,
        tts_api_key: needTtsKey ? ttsKey.trim() || null : null,
      });
      setLlmKey("");
      setSttKey("");
      setTtsKey("");
      setNote("Tester agent saved.");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const providerRows = TARGET_PLATFORMS.map((p) => {
    const count = agents.filter(
      (a) => (a.platform || "").toLowerCase() === p.id,
    ).length;
    const connected =
      Boolean(keys[p.env]) ||
      count > 0 ||
      (status?.platform || "").toLowerCase() === p.id;
    return { ...p, count, connected };
  });

  const defaultSuite =
    status?.suite_name ||
    agents.find((a) => a.suite)?.suite ||
    null;

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-7 pb-10">
      <header className="flex items-start justify-between gap-6 border-b border-border pb-5">
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-semibold tracking-[-0.005em] text-foreground">
            Settings
          </h1>
          <p className="mt-1 max-w-xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
            Edit the workspace configuration wiretap uses for every run. The same
            building blocks the setup wizard walked you through.
          </p>
        </div>
        <Button asChild variant="outline" className="shrink-0 rounded-[10px]">
          <Link to="/onboard?again=1">
            <RefreshCw data-icon="inline-start" className="size-3.5" />
            Re-run setup wizard
          </Link>
        </Button>
      </header>

      {error && <p className="text-sm text-fail">{error}</p>}
      {note && !error && <p className="text-sm text-muted-foreground">{note}</p>}

      {/* API keys · Tester agent */}
      <section className="flex flex-col gap-2.5">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          API keys · Tester agent
        </div>
        <div className="rounded-[14px] border border-border bg-card px-[22px] pt-[22px] pb-5">
          <div className="mb-1 flex items-center gap-2.5">
            <h2 className="text-[15px] font-semibold text-foreground">
              Tester agent
            </h2>
            {llmInfo && (
              <Badge
                variant="outline"
                className="h-auto rounded-full border-primary bg-accent px-2.5 py-0.5 text-[11.5px] font-medium text-primary"
              >
                {llmInfo.label}
              </Badge>
            )}
          </div>
          <p className="mb-[18px] text-[13px] leading-relaxed text-muted-foreground">
            The synthetic caller that runs your suites. LLM providers come from
            LiteLLM; STT/TTS use speech adapters (PyAI first). Keys stay in the
            local secret store — never shown here.
          </p>

          <TesterRow
            label="Speech-to-text"
            subLabel="transcribes the caller"
            first
          >
            <ProviderSelect
              value={stt}
              onChange={setStt}
              options={catalog?.stt || [{ id: "pyai", label: "PyAI" }]}
            />
            <SecretInput
              env={envLabel(sttInfo)}
              present={Boolean(sttInfo && keys[sttInfo.env])}
              value={sttKey}
              onChange={setSttKey}
              disabled={!needSttKey && Boolean(sttInfo && llmInfo && sttInfo.env === llmInfo.env)}
              sharedHint={
                !needSttKey && sttInfo && llmInfo && sttInfo.env === llmInfo.env
                  ? `Uses ${sttInfo.env}`
                  : undefined
              }
            />
          </TesterRow>

          <TesterRow label="Text-to-speech" subLabel="voices the tester agent">
            <ProviderSelect
              value={tts}
              onChange={onTtsChange}
              options={catalog?.tts || [{ id: "pyai", label: "PyAI" }]}
            />
            <SecretInput
              env={envLabel(ttsInfo)}
              present={Boolean(ttsInfo && keys[ttsInfo.env])}
              value={ttsKey}
              onChange={setTtsKey}
              disabled={
                !needTtsKey &&
                Boolean(
                  ttsInfo &&
                    ((llmInfo && ttsInfo.env === llmInfo.env) ||
                      (sttInfo && ttsInfo.env === sttInfo.env)),
                )
              }
              sharedHint={
                !needTtsKey && ttsInfo
                  ? `Uses ${ttsInfo.env}`
                  : undefined
              }
            />
          </TesterRow>

          <TesterRow label="LLM" subLabel="drives the tester’s replies">
            <ProviderSelect
              value={llm}
              onChange={onLlmChange}
              options={catalog?.llm || [{ id: "openai", label: "OpenAI" }]}
            />
            <SecretInput
              env={envLabel(llmInfo)}
              present={Boolean(llmInfo && keys[llmInfo.env])}
              value={llmKey}
              onChange={setLlmKey}
              onBlur={() => {
                if (llmKey.trim()) void loadModels(llm, llmKey);
              }}
            />
          </TesterRow>

          <TesterRow label="Simulator model" subLabel="caller turns">
            <ModelSelect
              value={simulatorModel}
              onChange={setSimulatorModel}
              options={modelOptions}
              className="sm:col-span-2"
            />
          </TesterRow>

          <TesterRow label="Judge model" subLabel="scores the call">
            <ModelSelect
              value={judgeModel}
              onChange={setJudgeModel}
              options={modelOptions}
              className="sm:col-span-2"
            />
          </TesterRow>

          {voiceOptions.length > 0 || voice ? (
            <TesterRow label="Voice" subLabel="TTS voice id">
              {voiceOptions.length > 0 ? (
                <div className="sm:col-span-2">
                  <AppSelect
                    value={voice || voiceOptions[0]?.id}
                    onValueChange={setVoice}
                    options={voiceOptions.map((v) => ({
                      value: v.id,
                      label: v.label || v.id,
                    }))}
                    placeholder="Voice"
                  />
                </div>
              ) : (
                <Input
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                  className="h-10 rounded-[10px] font-mono text-[13px] sm:col-span-2"
                  placeholder="voice id"
                />
              )}
            </TesterRow>
          ) : null}

          <div className="mt-5 flex justify-end">
            <Button onClick={saveTester} disabled={busy}>
              {busy ? "Saving…" : "Save tester agent"}
            </Button>
          </div>
        </div>
      </section>

      {/* Connected providers · Target agent */}
      <section className="flex flex-col gap-2.5">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          Connected providers · Target agent
        </div>
        <div className="rounded-[14px] border border-border bg-card px-[22px] py-1.5">
          {providerRows.map((p, i) => (
            <div
              key={p.id}
              className={cn(
                "flex items-center gap-4 py-4",
                i > 0 && "border-t border-border",
              )}
            >
              <span
                className={cn(
                  "size-2.5 shrink-0 rounded-full",
                  p.connected
                    ? "bg-[var(--wt-green-600)]"
                    : "bg-muted-foreground/40",
                )}
              />
              <div className="flex min-w-0 flex-1 items-baseline gap-2.5">
                <span className="text-[14.5px] font-semibold text-foreground">
                  {p.label}
                </span>
                {p.count > 0 && (
                  <span className="text-[12.5px] text-[var(--wt-text-muted)]">
                    · {p.count} agent{p.count === 1 ? "" : "s"}
                  </span>
                )}
              </div>
              {p.connected ? (
                <>
                  <Badge
                    variant="outline"
                    className="h-auto rounded-full border-primary bg-accent px-3 py-1 text-xs font-medium text-primary"
                  >
                    Connected
                  </Badge>
                  <Button asChild variant="ghost" size="sm" className="rounded-lg">
                    <Link to="/agents">Manage</Link>
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  className="rounded-[10px]"
                  onClick={() => {
                    setConnectPlatform(p.id);
                    setConnectOpen(true);
                  }}
                >
                  Connect
                </Button>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Defaults */}
      <section className="flex flex-col gap-2.5">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          Defaults
        </div>
        <div className="rounded-[14px] border border-border bg-card px-[22px] py-[22px]">
          <h2 className="mb-1 text-[15px] font-semibold text-foreground">
            Defaults
          </h2>
          <p className="mb-[18px] text-[13px] leading-relaxed text-muted-foreground">
            Pre-filled on every new run. Override per run any time.
          </p>

          <div className="grid grid-cols-1 items-center gap-x-5 gap-y-3 border-t border-border py-3 sm:grid-cols-[220px_1fr]">
            <div className="text-[13.5px] font-medium text-foreground">
              Default suite
            </div>
            <Input
              readOnly
              value={defaultSuite || "No suite yet"}
              className="h-10 rounded-[10px] bg-[var(--wt-section)] text-[13.5px]"
            />
          </div>

          <div className="grid grid-cols-1 items-center gap-x-5 gap-y-3 border-t border-border py-3 sm:grid-cols-[220px_1fr]">
            <div className="text-[13.5px] font-medium text-foreground">
              Concurrency
            </div>
            <div className="flex flex-wrap items-center gap-3.5">
              <div className="inline-flex items-center overflow-hidden rounded-[10px] border border-border bg-[var(--wt-section)]">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="rounded-none"
                  onClick={() => bumpConcurrency(-1)}
                  aria-label="Decrease concurrency"
                >
                  <Minus className="size-3.5" />
                </Button>
                <div className="min-w-9 border-x border-border px-[18px] py-1.5 text-center font-mono text-sm font-medium tabular-nums">
                  {concurrency}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="rounded-none"
                  onClick={() => bumpConcurrency(1)}
                  aria-label="Increase concurrency"
                >
                  <Plus className="size-3.5" />
                </Button>
              </div>
              <span className="font-mono text-[12.5px] text-[var(--wt-text-muted)]">
                parallel calls
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-2.5">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          Phone testing · PSTN
        </div>
        <PhoneTestingCard />
      </section>

      <ConnectAgentDialog
        open={connectOpen}
        onOpenChange={setConnectOpen}
        initialPlatform={connectPlatform}
        onConnected={() => {
          void refresh().catch((e: Error) => setError(e.message));
        }}
      />
    </div>
  );
}

function TesterRow({
  label,
  subLabel,
  first,
  children,
}: {
  label: string;
  subLabel: string;
  first?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 items-center gap-x-5 gap-y-3 py-3.5 sm:grid-cols-[220px_1fr]",
        !first && "border-t border-border",
      )}
    >
      <div className="min-w-0">
        <div className="mb-0.5 text-[13.5px] font-medium text-foreground">
          {label}
        </div>
        <div className="font-mono text-[11.5px] text-[var(--wt-text-muted)]">
          {subLabel}
        </div>
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-2.5 sm:grid-cols-[minmax(140px,180px)_1fr]">
        {children}
      </div>
    </div>
  );
}

function ProviderSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { id: string; label: string }[];
}) {
  return (
    <AppSelect
      value={value}
      onValueChange={onChange}
      options={options.map((p) => ({ value: p.id, label: p.label }))}
      placeholder="Provider"
    />
  );
}

function ModelSelect({
  value,
  onChange,
  options,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  className?: string;
}) {
  if (!options.length) {
    return (
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn("h-10 rounded-[10px] font-mono text-[13px]", className)}
        placeholder="model id"
      />
    );
  }
  const list = value && !options.includes(value) ? [value, ...options] : options;
  return (
    <div className={className}>
      <AppSelect
        mono
        value={value || list[0]}
        onValueChange={onChange}
        options={list.map((m) => ({ value: m, label: m }))}
        placeholder="Model"
      />
    </div>
  );
}

function SecretInput({
  env,
  present,
  value,
  onChange,
  onBlur,
  disabled,
  sharedHint,
}: {
  env: string;
  present: boolean;
  value: string;
  onChange: (v: string) => void;
  onBlur?: () => void;
  disabled?: boolean;
  sharedHint?: string;
}) {
  const [show, setShow] = useState(false);

  if (disabled && sharedHint) {
    return (
      <div className="flex h-10 items-center rounded-[10px] border border-border bg-[var(--wt-section)] px-3.5 font-mono text-[12.5px] text-muted-foreground">
        {sharedHint}
      </div>
    );
  }

  return (
    <div className="relative min-w-0">
      <Input
        type={show ? "text" : "password"}
        autoComplete="off"
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={present ? "•••• set locally — enter to replace" : `${env}`}
        className="h-10 rounded-[10px] pr-10 font-mono text-[13px] tracking-wide"
      />
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="absolute top-1/2 right-1.5 -translate-y-1/2 text-muted-foreground"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "Hide key" : "Show key"}
        tabIndex={-1}
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </Button>
    </div>
  );
}
