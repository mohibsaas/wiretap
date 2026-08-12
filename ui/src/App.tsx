import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { RequireOnboarded } from "@/components/RequireOnboarded";
import { AgentsPage } from "@/pages/AgentsPage";
import { BatchPage } from "@/pages/BatchPage";
import { EvaluationsPage } from "@/pages/EvaluationsPage";
import { HomeRedirect } from "@/pages/HomeRedirect";
import { OnboardGate } from "@/pages/OnboardGate";
import { SimulationDetailPage } from "@/pages/SimulationDetailPage";
import { SuiteDetailPage } from "@/pages/SuiteDetailPage";
import { SuitesPage } from "@/pages/SuitesPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* First-run only — not in the main sidebar */}
        <Route path="onboard" element={<OnboardGate />} />

        <Route element={<RequireOnboarded />}>
          <Route element={<AppShell />}>
            <Route index element={<HomeRedirect />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="suites" element={<SuitesPage />} />
            <Route path="suites/:name" element={<SuiteDetailPage />} />
            <Route path="evaluations" element={<EvaluationsPage />} />
            <Route
              path="evaluations/:simulationId"
              element={<SimulationDetailPage />}
            />
            <Route path="simulations" element={<Navigate to="/evaluations" replace />} />
            <Route path="batches/:batchId" element={<BatchPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
