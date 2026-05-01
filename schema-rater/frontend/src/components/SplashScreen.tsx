import { useEffect, useState } from "react";

interface Props {
  onSelectPathway: (pathway: "admin" | "client") => void;
}

type Phase = "title" | "fadeout" | "choices";

export default function SplashScreen({ onSelectPathway }: Props) {
  const [phase, setPhase] = useState<Phase>("title");

  useEffect(() => {
    const t1 = setTimeout(() => setPhase("fadeout"), 2500);
    const t2 = setTimeout(() => setPhase("choices"), 3100);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      <header className="topbar">
        <button onClick={() => onSelectPathway("admin")} className="flex items-center gap-3 hover:opacity-80 transition-opacity text-left">
          <div className="brand-mark schema-brand-mark">CR</div>
          <div className="topbar-copy">
            <h1>Cogitate Rater Engine</h1>
            <p>Unified rating workspace</p>
            <span className="type-badge type-badge-schema">Schema</span>
          </div>
        </button>

        <span className="workspace-pill workspace-pill-client">Pathway Select</span>
        <div className="topbar-actions">
          <button
            onClick={() => onSelectPathway("admin")}
            className="link-btn mode-inactive"
          >
            Admin
          </button>
          <button
            onClick={() => onSelectPathway("client")}
            className="link-btn mode-inactive"
          >
            Client
          </button>
        </div>
      </header>

      <div className="flex-1 flex items-center justify-center px-6 py-10">
        {/* Title phase */}
        <div className="text-center px-6 max-w-4xl w-full">
          {(phase === "title" || phase === "fadeout") && (
            <div className={phase === "fadeout" ? "animate-fade-out" : "animate-fade-in-up"}>
              <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight splash-title leading-tight">
                Choose your
                <br />
                workspace
              </h1>
              <p className="mt-4 text-lg text-slate-500 font-light">
                Unified insurance rating shell with a single engine badge.
              </p>
            </div>
          )}

          {/* Pathway choice phase */}
          {phase === "choices" && (
            <div className="animate-fade-in space-y-8">
              <div>
                <h2 className="text-2xl font-semibold text-slate-800">
                  Choose your pathway
                </h2>
                <p className="text-sm text-slate-500 mt-2">
                  Select how you'd like to use the platform
                </p>
              </div>

              <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
                <button
                  onClick={() => onSelectPathway("admin")}
                  className="group w-64 rounded-2xl border border-slate-200 bg-white px-8 py-8 shadow-lg hover:shadow-xl hover:border-slate-300 transition-all duration-300"
                >
                  <div className="text-4xl mb-3">🛠️</div>
                  <h3 className="text-xl font-bold text-slate-900 transition-colors">
                    Admin
                  </h3>
                  <p className="text-sm text-slate-500 mt-2">
                    Upload &amp; manage rater workbooks
                  </p>
                </button>

                <button
                  onClick={() => onSelectPathway("client")}
                  className="group w-64 rounded-2xl border border-slate-200 bg-white px-8 py-8 shadow-lg hover:shadow-xl hover:border-slate-300 transition-all duration-300"
                >
                  <div className="text-4xl mb-3">📊</div>
                  <h3 className="text-xl font-bold text-slate-900 transition-colors">
                    Client
                  </h3>
                  <p className="text-sm text-slate-500 mt-2">
                    Calculate premiums with existing raters
                  </p>
                </button>
              </div>
              <div className="mt-8 pt-4">
                <a
                  href="/gateway/home"
                  className="text-sm text-slate-400 hover:text-slate-600 underline underline-offset-4 transition-colors"
                >
                  Return to Gateway Home
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
