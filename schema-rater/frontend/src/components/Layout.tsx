import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

interface Props {
  children: ReactNode;
  mode: "admin" | "client";
}

export default function Layout({ children, mode }: Props) {
  const navigate = useNavigate();

  const isAdmin = mode === "admin";
  const badgeLabel = "Schema";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      <header className="topbar schema-topbar">
        <button onClick={() => navigate(`/${mode}`)} className="flex items-center gap-3 hover:opacity-80 transition-opacity text-left">
          <div className="brand-mark schema-brand-mark">CR</div>
          <div className="topbar-copy">
            <h1>Cogitate Rater Engine</h1>
            <p>Unified rating workspace</p>
            <span className={`type-badge ${isAdmin ? "type-badge-schema" : "type-badge-schema"}`}>
              {badgeLabel}
            </span>
          </div>
        </button>

        <span className={`workspace-pill ${isAdmin ? "workspace-pill-admin" : "workspace-pill-client"}`}>
          {isAdmin ? "Admin Workspace" : "Client Workspace"}
        </span>

        <div className="topbar-actions">
          <button
            onClick={() => navigate("/admin")}
            className={isAdmin ? "link-btn link-btn-solid mode-active" : "link-btn mode-inactive"}
          >
            Admin
          </button>
          <button
            onClick={() => navigate("/client")}
            className={!isAdmin ? "link-btn link-btn-solid mode-active" : "link-btn mode-inactive"}
          >
            Client
          </button>
        </div>
      </header>

      <main className="schema-main">{children}</main>
    </div>
  );
}
