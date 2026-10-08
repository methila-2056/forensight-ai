import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import AssistantPage from "./pages/AssistantPage";
import CaseDetailPage from "./pages/CaseDetailPage";
import CaseListPage from "./pages/CaseListPage";
import CreateCasePage from "./pages/CreateCasePage";
import EventsPage from "./pages/EventsPage";
import FindingDetailPage from "./pages/FindingDetailPage";
import FindingsPage from "./pages/FindingsPage";
import InvestigationPage from "./pages/InvestigationPage";
import Landing from "./pages/Landing";

export default function App(): JSX.Element {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Landing />} />
          <Route path="/cases" element={<CaseListPage />} />
          <Route path="/cases/new" element={<CreateCasePage />} />
          <Route path="/cases/:caseId/events" element={<EventsPage />} />
          <Route path="/cases/:caseId/findings" element={<FindingsPage />} />
          <Route
            path="/cases/:caseId/findings/:findingId"
            element={<FindingDetailPage />}
          />
          <Route
            path="/cases/:caseId/investigation"
            element={<InvestigationPage />}
          />
          <Route path="/cases/:caseId/assistant" element={<AssistantPage />} />
          <Route path="/cases/:caseId" element={<CaseDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
