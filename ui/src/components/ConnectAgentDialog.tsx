import { useEffect, useMemo, useState } from "react";
import { client, type OnboardStatus } from "@/lib/api";
import {
  AppModal,
  modalFieldClass,
  modalFieldsClass,
  modalHintClass,
  modalInputClass,
  modalLabelClass,
} from "@/components/AppModal";
import { AppSelect } from "@/components/AppSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const PLATFORMS = [
  { value: "retell", label: "Retell" },
  { value: "vapi", label: "Vapi" },
  { value: "elevenlabs", label: "ElevenLabs Agents" },
  { value: "livekit", label: "LiveKit Agents" },
  { value: "synthflow", label: "Synthflow" },
  { value: "bolna", label: "Bolna (import only)" },
  { value: "custom", label: "Custom (text stub)" },
] as const;

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Prefill platform when opening from a provider row. */
  initialPlatform?: string | null;
  onConnected?: () => void;
};

/**
 * Connect / add a target agent without leaving the current page.
 * Mirrors onboard “add agent” (platform + credentials + agent id).
 */
export function ConnectAgentDialog({
  open,
  onOpenChange,
  initialPlatform,
  onConnected,
}: Props) {
  const [status, setStatus] = useState<OnboardStatus | null>(null);
  const [platform, setPlatform] = useState("retell");
  const [agentId, setAgentId] = useState("");
  const [remoteAgents, setRemoteAgents] = useState<
    { id: string; name: string; label: string }[] | null
  >(null);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [roomUrl, setRoomUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentsLoading, setAgentsLoading] = useState(false);

  const platformNeedsKey = platform !== "custom";
  const platformKeyEnv =
    platform === "livekit"
      ? "LIVEKIT_API_KEY"
      : `${platform.toUpperCase()}_API_KEY`;
  const platformKeyAlreadySet = Boolean(status?.keys?.[platformKeyEnv]);
  const showPlatformKey = platformNeedsKey && !platformKeyAlreadySet;
  const showLivekitSecret =
    platform === "livekit" &&
    !status?.keys?.LIVEKIT_TOKEN &&
    !status?.keys?.LIVEKIT_API_SECRET;
  const showRoomUrl = platform === "livekit";
  const supportsLiveAgents = ["retell", "vapi", "elevenlabs"].includes(platform);

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
    if (!open) return;
    setError(null);
    setApiKey("");
    setApiSecret("");
    setRoomUrl("");
    setAgentId("");
    setRemoteAgents(null);
    setBusy(false);
    setAgentsLoading(false);

    const pick =
      initialPlatform &&
      PLATFORMS.some((p) => p.value === initialPlatform)
        ? initialPlatform
        : "retell";
    setPlatform(pick);

    let cancelled = false;
    void client
      .onboardStatus()
      .then(async (s) => {
        if (cancelled) return;
        setStatus(s);
        if (!["retell", "vapi", "elevenlabs"].includes(pick)) {
          setRemoteAgents(null);
          setAgentsLoading(false);
          return;
        }
        setAgentsLoading(true);
        try {
          const res = await client.platformAgents(pick, null);
          if (cancelled) return;
          if (res.source === "live" && res.agents.length) {
            setRemoteAgents(res.agents);
            setAgentId(res.agents[0].id);
          } else {
            setRemoteAgents(null);
          }
        } catch {
          if (!cancelled) setRemoteAgents(null);
        } finally {
          if (!cancelled) setAgentsLoading(false);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });

    return () => {
      cancelled = true;
    };
  }, [open, initialPlatform]);

  const canConnect = useMemo(() => {
    if (platform !== "custom" && !agentId.trim()) return false;
    if (showPlatformKey && !apiKey.trim()) return false;
    if (
      showLivekitSecret &&
      !apiSecret.trim() &&
      !status?.keys?.LIVEKIT_TOKEN
    ) {
      return false;
    }
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

  async function connect() {
    if (!canConnect) return;
    setBusy(true);
    setError(null);
    try {
      await client.connect({
        platform,
        agent_id: agentId.trim() || null,
        api_key: showPlatformKey && apiKey.trim() ? apiKey.trim() : null,
        api_secret:
          platform === "livekit" && apiSecret.trim()
            ? apiSecret.trim()
            : null,
        room_url: showRoomUrl && roomUrl.trim() ? roomUrl.trim() : null,
      });
      setApiKey("");
      setApiSecret("");
      onOpenChange(false);
      onConnected?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppModal
      open={open}
      onOpenChange={onOpenChange}
      title="Connect agent"
      description="Link a live voice agent. Keys stay in the local secret store — never shown again."
      maxWidthClass="sm:max-w-[480px]"
      footer={
        <>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button onClick={connect} disabled={busy || !canConnect}>
            {busy ? "Connecting…" : "Connect"}
          </Button>
        </>
      }
    >
      <div className={modalFieldsClass}>
        <div className={modalFieldClass}>
          <Label htmlFor="connect-platform" className={modalLabelClass}>
            Platform
          </Label>
          <AppSelect
            id="connect-platform"
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
        </div>

        {showRoomUrl ? (
          <div className={modalFieldClass}>
            <Label htmlFor="connect-room" className={modalLabelClass}>
              LiveKit URL
            </Label>
            <Input
              id="connect-room"
              className={modalInputClass}
              value={roomUrl}
              onChange={(e) => setRoomUrl(e.target.value)}
              placeholder="wss://your-project.livekit.cloud"
              autoComplete="off"
            />
          </div>
        ) : null}

        {platformNeedsKey ? (
          <>
            {showPlatformKey ? (
              <div className={modalFieldClass}>
                <Label htmlFor="connect-key" className={modalLabelClass}>
                  {platformKeyEnv}
                </Label>
                <Input
                  id="connect-key"
                  type="password"
                  autoComplete="off"
                  className={cn(modalInputClass, "font-mono")}
                  placeholder="API key"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  onBlur={() => {
                    if (apiKey.trim()) void refreshAgents(platform, apiKey);
                  }}
                />
                <p className={modalHintClass}>
                  Blur the field after entering a key to load agents.
                </p>
              </div>
            ) : (
              <p className={modalHintClass}>
                Using existing {platformKeyEnv} from .env
              </p>
            )}

            {showLivekitSecret ? (
              <div className={modalFieldClass}>
                <Label htmlFor="connect-secret" className={modalLabelClass}>
                  LIVEKIT_API_SECRET
                </Label>
                <Input
                  id="connect-secret"
                  type="password"
                  autoComplete="off"
                  className={cn(modalInputClass, "font-mono")}
                  placeholder="API secret"
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                />
              </div>
            ) : null}

            <div className={modalFieldClass}>
              <Label htmlFor="connect-agent" className={modalLabelClass}>
                {platform === "livekit"
                  ? "Room name"
                  : platform === "synthflow"
                    ? "Model / assistant ID"
                    : "Agent"}
              </Label>
              {agentsLoading && supportsLiveAgents ? (
                <AppSelect
                  id="connect-agent"
                  disabled
                  value="__loading__"
                  onValueChange={() => {}}
                  placeholder="Loading…"
                  options={[
                    {
                      value: "__loading__",
                      label: "Loading…",
                      disabled: true,
                    },
                  ]}
                />
              ) : remoteAgents && remoteAgents.length > 0 ? (
                <AppSelect
                  id="connect-agent"
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
              ) : null}
              {!agentsLoading &&
                (!remoteAgents?.length ||
                  !remoteAgents.some((a) => a.id === agentId)) && (
                  <Input
                    id={remoteAgents?.length ? undefined : "connect-agent"}
                    className={modalInputClass}
                    value={agentId}
                    onChange={(e) => setAgentId(e.target.value)}
                    placeholder={
                      platform === "livekit" ? "my-agent-room" : "agent_xxx"
                    }
                  />
                )}
            </div>

            {platform === "bolna" ? (
              <p className={modalHintClass}>
                Bolna import drafts a suite; live phone dial is not wired yet.
              </p>
            ) : null}
            {platform === "synthflow" ? (
              <p className={modalHintClass}>
                Live dial also needs SYNTHFLOW_FROM_NUMBER /
                SYNTHFLOW_TO_NUMBER in .env.
              </p>
            ) : null}
          </>
        ) : (
          <div className={modalFieldClass}>
            <Label htmlFor="connect-name" className={modalLabelClass}>
              Name (optional)
            </Label>
            <Input
              id="connect-name"
              className={modalInputClass}
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              placeholder="my-agent"
            />
          </div>
        )}

        {error && <p className="text-sm text-fail">{error}</p>}
      </div>
    </AppModal>
  );
}
