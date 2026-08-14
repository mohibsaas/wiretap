import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { client } from "@/lib/api";

/**
 * Until first-run setup completes, keep the user on the dashboard where the
 * onboarding modal opens over the blurred shell.
 */
export function RequireOnboarded() {
  const location = useLocation();
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
  }, [location.pathname]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  const onDashboard =
    location.pathname === "/" || location.pathname === "/dashboard";

  if (needs && !onDashboard) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
