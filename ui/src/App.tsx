import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useParams,
} from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { RequireOnboarded } from "@/components/RequireOnboarded";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AgentsPage } from "@/pages/AgentsPage";
import { BatchPage } from "@/pages/BatchPage";
import { CategoriesPage } from "@/pages/CategoriesPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { EvaluationsPage } from "@/pages/EvaluationsPage";
import { HomeRedirect } from "@/pages/HomeRedirect";
import { OnboardGate } from "@/pages/OnboardGate";
import { SettingsPage } from "@/pages/SettingsPage";
import { ReportDetailPage } from "@/pages/ReportDetailPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SimulationDetailPage } from "@/pages/SimulationDetailPage";
import { SuiteDetailPage } from "@/pages/SuiteDetailPage";
import { SuitesPage } from "@/pages/SuitesPage";

function RedirectEvaluationRun() {
  const { batchId = "" } = useParams();
  const q = batchId ? `?run=${encodeURIComponent(batchId)}` : "";
  return <Navigate to={`/evaluations${q}`} replace />;
}

function RedirectSuiteEdit() {
  const { name = "" } = useParams();
  return (
    <Navigate to={`/suites/${encodeURIComponent(name)}`} replace />
  );
}

export default function App() {
  return (
    <TooltipProvider>
      <BrowserRouter>
        <Routes>
          <Route path="onboard" element={<OnboardGate />} />

          <Route element={<RequireOnboarded />}>
            <Route element={<AppShell />}>
              <Route index element={<HomeRedirect />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="reports/:batchId" element={<ReportDetailPage />} />
              <Route path="agents" element={<AgentsPage />} />
              <Route path="suites" element={<SuitesPage />} />
              <Route path="categories" element={<CategoriesPage />} />
              <Route path="suites/:name/edit" element={<RedirectSuiteEdit />} />
              <Route path="suites/:name" element={<SuiteDetailPage />} />
              <Route path="evaluations" element={<EvaluationsPage />} />
              <Route
                path="evaluations/:batchId"
                element={<RedirectEvaluationRun />}
              />
              <Route
                path="evaluations/:batchId/scenarios/:simulationId"
                element={<SimulationDetailPage />}
              />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="simulations" element={<Navigate to="/evaluations" replace />} />
              <Route path="batches/:batchId" element={<BatchPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  );
}
