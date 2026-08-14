import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { PhoneTestingCard } from "@/components/PhoneTestingCard";
import { client, type OnboardStatus } from "@/lib/api";

export function SettingsPage() {
  const [status, setStatus] = useState<OnboardStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .onboardStatus()
      .then(setStatus)
      .catch((e: Error) => setError(e.message));
  }, []);

  const caller = status?.caller;
  // Twilio keys belong to phone testing below, not to the tester agent stack.
  const callerKeys = Object.entries(status?.keys ?? {}).filter(
    ([name]) => !name.startsWith("TWILIO_"),
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-5 border-b border-border pb-5">
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-semibold tracking-[-0.005em] text-foreground">
            Settings
          </h1>
          <p className="mt-1 max-w-xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
            Edit the workspace configuration wiretap uses for every run. The same
            building blocks the setup wizard walked you through.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to="/onboard?again=1">
            <RefreshCw data-icon="inline-start" />
            Re-run setup wizard
          </Link>
        </Button>
      </header>

      {error && <p className="text-sm text-fail">{error}</p>}

      <section className="flex flex-col gap-2.5">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          API keys · Tester agent
        </div>
        <Card className="ring-border">
          <CardHeader>
            <div className="flex items-center gap-2.5">
              <CardTitle>Tester agent</CardTitle>
              {caller?.llm_provider && (
                <Badge variant="outline" className="border-primary bg-accent text-primary">
                  {caller.llm_provider}
                </Badge>
              )}
            </div>
            <CardDescription>
              The synthetic caller that runs your suites. Keys stay in local env /
              config — never shown here.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <Meta label="Simulator model" value={caller?.simulator_model} />
              <Meta label="Judge model" value={caller?.judge_model} />
              <Meta label="STT" value={caller?.stt} />
              <Meta label="TTS / voice" value={[caller?.tts, caller?.voice].filter(Boolean).join(" · ")} />
            </div>
            <Separator />
            <div className="flex flex-wrap gap-2">
              {callerKeys.map(([name, present]) => (
                <Badge key={name} variant={present ? "pass" : "muted"}>
                  {name}: {present ? "set" : "missing"}
                </Badge>
              ))}
              {callerKeys.length === 0 && (
                <span className="text-sm text-muted-foreground">No key status yet.</span>
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-2.5">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          Connected providers · Target agent
        </div>
        <Card className="ring-border">
          <CardHeader>
            <CardTitle>Target agent</CardTitle>
            <CardDescription>
              Platform agent under evaluation. Add another via onboarding or CLI import.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <Meta label="Platform" value={status?.platform} />
            <Meta label="Agent" value={status?.agent_name || status?.agent_id} />
            <Meta label="Suites" value={String(status?.suite_count ?? 0)} />
            <div>
              <Button asChild variant="outline" size="sm">
                <Link to="/agents">Manage agents</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-2.5">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
          Phone testing · PSTN
        </div>
        <PhoneTestingCard />
      </section>
    </div>
  );
}

function Meta({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium text-foreground">{value || "—"}</div>
    </div>
  );
}
