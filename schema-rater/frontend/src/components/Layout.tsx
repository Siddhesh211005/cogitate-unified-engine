import type { ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";

interface Props {
  children: ReactNode;
  mode: "admin" | "client";
}

export default function Layout({ children, mode }: Props) {
  const navigate = useNavigate();
  const location = useLocation();

  const isAdmin = mode === "admin";

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(`/${mode}`)}
              className="flex items-center gap-3 hover:opacity-80 transition-opacity"
            >
              <div
                className={`${
                  isAdmin
                    ? "bg-orange-500"
                    : "bg-blue-600"
                } text-white font-bold rounded-lg px-3 py-1.5 text-sm`}
              >
                CR
              </div>
              <div className="text-left">
                <h1 className="text-lg font-bold text-gray-900">
                  Cogitate Rater Engine
                </h1>
                <p className="text-xs text-gray-500">
                  {isAdmin ? "Admin Panel" : "Client Portal"}
                </p>
              </div>
            </button>
          </div>

          <div className="flex items-center gap-4">
            {/* Current path breadcrumb */}
            <span
              className={`text-xs font-medium px-3 py-1 rounded-full ${
                isAdmin
                  ? "bg-orange-50 text-orange-600"
                  : "bg-blue-50 text-blue-600"
              }`}
            >
              {isAdmin ? "🛠️ Admin" : "📊 Client"}
            </span>

            {/* Back to dashboard */}
            {location.pathname !== `/${mode}` && (
              <button
                onClick={() => navigate(`/${mode}`)}
                className={`text-sm font-medium ${
                  isAdmin
                    ? "text-orange-600 hover:text-orange-800"
                    : "text-blue-600 hover:text-blue-800"
                } transition-colors`}
              >
                ← Dashboard
              </button>
            )}

            {/* Switch pathway */}
            <button
              onClick={() => navigate("/")}
              className="text-sm text-gray-500 hover:text-gray-700 font-medium transition-colors"
            >
              Switch Pathway
            </button>

            {/* Switch Rater Engine */}
            <a
              href="/gateway/home"
              className="text-sm bg-gray-800 text-white px-4 py-1.5 rounded-md hover:bg-gray-700 font-semibold transition-colors shadow-sm ml-2"
            >
              Switch Rater Engine
            </a>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 py-8 flex-1 w-full">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 text-center text-xs text-gray-400">
          Cogitate Rater Engine v3.0 &middot; Dynamic Excel-to-UI premium
          calculation
        </div>
      </footer>
    </div>
  );
}
