import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { client } from "@/lib/api";
import { OnboardPage } from "@/pages/OnboardPage";

/** Full-screen first-run only — not part of the main nav. */
export function OnboardGate() {
  const [ready, setReady] = useState(false);
  const [needs, setNeeds] = useState(true);

  useEffect(() => {
    client
      .onboardStatus()
      .then((s) => {
        setNeeds(s.needs_onboarding);
        setReady(true);
      })
      .catch(() => {
        // If status fails, don't trap the user in onboarding
        setNeeds(false);
        setReady(true);
      });
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }
  if (!needs) {
    return <Navigate to="/suites" replace />;
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card px-6 py-4">
        <div className="mx-auto max-w-2xl">
          <div className="text-lg font-semibold tracking-tight">wiretap</div>
          <div className="text-xs text-muted-foreground">First-time setup</div>
        </div>
      </header>
      <div className="px-6 py-8">
        <OnboardPage />
      </div>
    </div>
  );
}
