import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { client } from "@/lib/api";

export function HomeRedirect() {
  const navigate = useNavigate();
  const [done, setDone] = useState(false);

  useEffect(() => {
    client
      .onboardStatus()
      .then((s) => {
        navigate(s.needs_onboarding ? "/onboard" : "/suites", { replace: true });
      })
      .catch(() => navigate("/suites", { replace: true }))
      .finally(() => setDone(true));
  }, [navigate]);

  if (!done) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  return <Navigate to="/suites" replace />;
}
