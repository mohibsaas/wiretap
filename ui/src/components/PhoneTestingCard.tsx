import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { AppSelect } from "@/components/AppSelect";
import { client, type PstnStatus, type TwilioNumber } from "@/lib/api";

const ACCOUNT_SID = "TWILIO_ACCOUNT_SID";
const AUTH_TOKEN = "TWILIO_AUTH_TOKEN";
const SIP_PASSWORD = "TWILIO_SIP_PASSWORD";

type Props = {
  onStatusChange?: (status: PstnStatus) => void;
};

/** Twilio credentials + caller number for `simulate --transport phone`.
 *
 * Write-only by design: the API reports presence, so a stored value can be
 * replaced here but never read back.
 */
export function PhoneTestingCard({ onStatusChange }: Props) {
  const [status, setStatus] = useState<PstnStatus | null>(null);
  const [sid, setSid] = useState("");
  const [token, setToken] = useState("");
  const [numbers, setNumbers] = useState<TwilioNumber[] | null>(null);
  const [pick, setPick] = useState("");
  const [savingKeys, setSavingKeys] = useState(false);
  const [loadingNumbers, setLoadingNumbers] = useState(false);
  const [savingNumber, setSavingNumber] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Held in a ref so a parent's inline callback cannot restart the fetch loop.
  const notify = useRef(onStatusChange);
  notify.current = onStatusChange;

  const refresh = useCallback(async () => {
    try {
      const next = await client.pstnStatus();
      setStatus(next);
      notify.current?.(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const keys = status?.keys ?? {};
  const hasCredentials = Boolean(status?.has_credentials);
  const extraMissing = Boolean(status && !status.extra_installed);
  // Distinguish "keys are missing" from "the phone extra is not installed" —
  // otherwise a stored credential still reads as unconfigured.
  const readiness = status?.ready
    ? { label: "ready", variant: "pass" as const }
    : extraMissing
      ? { label: "extra not installed", variant: "warn" as const }
      : { label: "not configured", variant: "warn" as const };

  async function saveCredentials() {
    const secrets: Record<string, string> = {};
    if (sid.trim()) secrets[ACCOUNT_SID] = sid.trim();
    if (token.trim()) secrets[AUTH_TOKEN] = token.trim();
    if (Object.keys(secrets).length === 0) return;
    setSavingKeys(true);
    setError(null);
    setNote(null);
    try {
      const res = await client.saveSecrets(secrets);
      setSid("");
      setToken("");
      setNumbers(null);
      setNote(`Saved ${res.updated.join(" · ")}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingKeys(false);
    }
  }

  async function loadNumbers() {
    setLoadingNumbers(true);
    setError(null);
    try {
      const res = await client.twilioNumbers();
      setNumbers(res.numbers);
      setPick(res.selected || res.numbers[0]?.phone_number || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingNumbers(false);
    }
  }

  async function saveNumber() {
    if (!pick.trim()) return;
    setSavingNumber(true);
    setError(null);
    setNote(null);
    try {
      const res = await client.saveFromNumber(pick.trim());
      setNote(`Dialing from ${res.selected}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingNumber(false);
    }
  }

  return (
    <Card className="ring-border">
      <CardHeader>
        <div className="flex items-center gap-2.5">
          <CardTitle>Phone testing</CardTitle>
          {status ? <Badge variant={readiness.variant}>{readiness.label}</Badge> : null}
        </div>
        <CardDescription>
          Dial the agent&apos;s real number over PSTN instead of connecting over the
          web. Credentials go to the local secret store and are never shown here.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {extraMissing && status && (
          <p className="text-sm text-warn">
            Credentials can be saved now, but calls need the phone extra:{" "}
            <code className="font-mono text-[13px]">uv sync --extra pstn</code>
            {status.missing_packages.length > 0
              ? ` — missing ${status.missing_packages.join(", ")}. `
              : ". "}
            Install it in whichever environment runs the server, then restart it.
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <Badge variant={keys[ACCOUNT_SID] ? "pass" : "muted"}>
            {ACCOUNT_SID}: {keys[ACCOUNT_SID] ? "set" : "missing"}
          </Badge>
          <Badge variant={keys[AUTH_TOKEN] ? "pass" : "muted"}>
            {AUTH_TOKEN}: {keys[AUTH_TOKEN] ? "set" : "missing"}
          </Badge>
          <Badge variant={keys[SIP_PASSWORD] ? "pass" : "muted"}>
            SIP password: {keys[SIP_PASSWORD] ? "provisioned" : "on first call"}
          </Badge>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="twilio-sid">Account SID</Label>
            <Input
              id="twilio-sid"
              type="password"
              autoComplete="off"
              className="h-10 rounded-[10px] font-mono text-[13px]"
              placeholder={keys[ACCOUNT_SID] ? "•••• stored — enter to replace" : "AC…"}
              value={sid}
              onChange={(e) => setSid(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="twilio-token">Auth token</Label>
            <Input
              id="twilio-token"
              type="password"
              autoComplete="off"
              className="h-10 rounded-[10px] font-mono text-[13px]"
              placeholder={keys[AUTH_TOKEN] ? "•••• stored — enter to replace" : "auth token"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={saveCredentials}
            disabled={savingKeys || (!sid.trim() && !token.trim())}
          >
            {savingKeys ? "Saving…" : "Save credentials"}
          </Button>
          <p className="text-xs text-muted-foreground">
            Both live in the Twilio Console dashboard. The SIP password is generated
            and stored for you on the first phone run.
          </p>
        </div>

        <Separator />

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex flex-col gap-0.5">
              <div className="text-xs text-muted-foreground">Caller number</div>
              <div className="font-medium text-foreground">
                {status?.from_number || "—"}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadNumbers}
              disabled={loadingNumbers || !hasCredentials || extraMissing}
            >
              <RefreshCw data-icon="inline-start" />
              {loadingNumbers ? "Loading…" : "Load my numbers"}
            </Button>
          </div>
          {!hasCredentials ? (
            <p className="text-xs text-muted-foreground">
              Save the Twilio credentials to list the numbers on your account.
            </p>
          ) : extraMissing ? (
            <p className="text-xs text-muted-foreground">
              Looking up numbers needs the twilio SDK — install the phone extra first.
            </p>
          ) : null}
          {numbers && (
            <div className="flex flex-col gap-2">
              {numbers.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No numbers on this Twilio account — buy one in the Twilio console,
                  or type an E.164 number below.
                </p>
              ) : (
                <AppSelect
                  aria-label="Caller number"
                  mono
                  value={
                    numbers.some((n) => n.phone_number === pick)
                      ? pick
                      : "__custom__"
                  }
                  onValueChange={(v) =>
                    setPick(v === "__custom__" ? "" : v)
                  }
                  options={[
                    ...numbers.map((n) => ({
                      value: n.phone_number,
                      label:
                        n.phone_number +
                        (n.friendly_name ? ` · ${n.friendly_name}` : ""),
                    })),
                    { value: "__custom__", label: "Type a number…" },
                  ]}
                />
              )}
              {(numbers.length === 0 || !numbers.some((n) => n.phone_number === pick)) && (
                <Input
                  className="h-10 rounded-[10px] font-mono text-[13px]"
                  placeholder="+14155550123"
                  value={pick}
                  onChange={(e) => setPick(e.target.value)}
                />
              )}
              <div>
                <Button size="sm" onClick={saveNumber} disabled={savingNumber || !pick.trim()}>
                  {savingNumber ? "Saving…" : "Use this number"}
                </Button>
              </div>
            </div>
          )}
        </div>

        {status && !status.ready && status.missing.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Still needed: {status.missing.join(" · ")}
          </p>
        )}
        {note && <p className="text-sm text-pass">{note}</p>}
        {error && <p className="text-sm text-fail">{error}</p>}
      </CardContent>
    </Card>
  );
}
