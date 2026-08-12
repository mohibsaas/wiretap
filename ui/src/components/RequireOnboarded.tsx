import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { client } from "@/lib/api";

/** Main app: only after onboarding is done (or suites already exist). */
export function RequireOnboarded() {
  const [ready, setReady] = useState(false);
  const [needs, setNeeds] = useState(false);

  useEffect(() => {
    client
      .onboardStatus()
      .then((s) => {
        setNeeds(s.needs_onboarding);
        setReady(true);
      })
      .catch(() => {
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
  if (needs) {
    return <Navigate to="/onboard" replace />;
  }
  return <Outlet />;
}
