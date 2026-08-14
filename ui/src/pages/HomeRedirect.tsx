import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { client } from "@/lib/api";
import { DashboardPage } from "@/pages/DashboardPage";

export function HomeRedirect() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [needsOnboard, setNeedsOnboard] = useState(false);

  useEffect(() => {
    client
      .onboardStatus()
      .then((s) => {
        if (s.needs_onboarding) {
          setNeedsOnboard(true);
          navigate("/onboard", { replace: true });
        }
      })
      .catch(() => {
        /* stay on dashboard */
      })
      .finally(() => setReady(true));
  }, [navigate]);

  if (!ready) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (needsOnboard) {
    return <Navigate to="/onboard" replace />;
  }
  return <DashboardPage />;
}
