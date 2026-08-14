import { Navigate, useSearchParams } from "react-router-dom";

/** Legacy `/onboard` → dashboard modal (`?again=1` preserved). */
export function OnboardGate() {
  const [params] = useSearchParams();
  const again = params.get("again") === "1";
  return <Navigate to={again ? "/?again=1" : "/"} replace />;
}
