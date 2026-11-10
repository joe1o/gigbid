// App.tsx - routes. Signed-out users go to /login; users who haven't onboarded go to /onboarding.
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout, { useTheme } from "./components/Layout";
import { Loading } from "./components/ui";
import { api, unwrap } from "./lib/api/client";
import { useLoad } from "./lib/hooks";
import AnalyticsPage from "./app/analytics/AnalyticsPage";
import AuthPage from "./app/auth/AuthPage";
import InboxPage from "./app/inbox/InboxPage";
import JobPage from "./app/jobs/JobPage";
import MessagesPage from "./app/messages/MessagesPage";
import OnboardingPage from "./app/onboarding/OnboardingPage";
import PipelinePage from "./app/pipeline/PipelinePage";
import RunPage from "./app/runs/RunPage";
import SettingsPage from "./app/settings/SettingsPage";
import StudioPage from "./app/studio/StudioPage";

function RequireUser({ children, onboarding = false }: { children: JSX.Element; onboarding?: boolean }) {
  const loc = useLocation();
  const me = useLoad(async () => {
    const r = await api.GET("/api/me");
    return r.response.status === 401 ? null : unwrap(r);
  }, [loc.pathname]);
  if (me.loading && !me.data) return <div className="main"><Loading /></div>;
  if (!me.data) return <Navigate to="/login" replace />;
  if (!onboarding && !me.data.onboarded) return <Navigate to="/onboarding" replace />;
  return children;
}

export default function App() {
  useTheme();
  return (
    <Routes>
      <Route path="/login" element={<AuthPage />} />
      {/* Different keys: React must NOT reuse one guard (and its stale "not onboarded" data) for the other. */}
      <Route path="/onboarding" element={<RequireUser key="onboarding" onboarding><OnboardingPage /></RequireUser>} />
      <Route element={<RequireUser key="app"><Layout /></RequireUser>}>
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/jobs/:id" element={<JobPage />} />
        <Route path="/studio/:id" element={<StudioPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/messages" element={<MessagesPage />} />
        <Route path="/messages/:threadId" element={<MessagesPage />} />
        <Route path="/runs/:threadId" element={<RunPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/inbox" replace />} />
    </Routes>
  );
}
