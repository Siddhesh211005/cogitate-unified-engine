import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import SplashScreen from "./components/SplashScreen";
import Layout from "./components/Layout";
import AdminDashboard from "./components/AdminDashboard";
import AdminRaterWorkspace from "./components/AdminRaterWorkspace";
import ClientDashboard from "./components/ClientDashboard";
import ClientRaterWorkspace from "./components/ClientRaterWorkspace";

// ── Splash wrapper (needs navigate hook) ──────────────────────────────────

function SplashPage() {
  const navigate = useNavigate();
  return (
    <SplashScreen
      onSelectPathway={(pathway) => navigate(`/${pathway}`)}
    />
  );
}

// ── Admin layout wrapper ──────────────────────────────────────────────────

function AdminPage({ children }: { children: React.ReactNode }) {
  return <Layout mode="admin">{children}</Layout>;
}

function ClientPage({ children }: { children: React.ReactNode }) {
  return <Layout mode="client">{children}</Layout>;
}

// ── App ───────────────────────────────────────────────────────────────────

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Splash / pathway selection */}
        <Route path="/" element={<SplashPage />} />

        {/* Admin pathway */}
        <Route
          path="/admin"
          element={
            <AdminPage>
              <AdminDashboard />
            </AdminPage>
          }
        />
        <Route
          path="/admin/rater/:raterId"
          element={
            <AdminPage>
              <AdminRaterWorkspace />
            </AdminPage>
          }
        />

        {/* Client pathway */}
        <Route
          path="/client"
          element={
            <ClientPage>
              <ClientDashboard />
            </ClientPage>
          }
        />
        <Route
          path="/client/rater/:raterId"
          element={
            <ClientPage>
              <ClientRaterWorkspace />
            </ClientPage>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
