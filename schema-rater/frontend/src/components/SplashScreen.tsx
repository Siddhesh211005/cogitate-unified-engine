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
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-100">
      <div className="text-center px-6">
        {/* Title phase */}
        {(phase === "title" || phase === "fadeout") && (
          <div className={phase === "fadeout" ? "animate-fade-out" : "animate-fade-in-up"}>
            <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight splash-title leading-tight">
              Welcome to
              <br />
              Cogitate Rater AI
            </h1>
            <p className="mt-4 text-lg text-gray-400 font-light">
              Intelligent Insurance Rating Platform
            </p>
          </div>
        )}

        {/* Pathway choice phase */}
        {phase === "choices" && (
          <div className="animate-fade-in space-y-8">
            <div>
              <h2 className="text-2xl font-semibold text-gray-800">
                Choose your pathway
              </h2>
              <p className="text-sm text-gray-500 mt-2">
                Select how you'd like to use the platform
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
              {/* Admin button */}
              <button
                onClick={() => onSelectPathway("admin")}
                className="group w-64 rounded-2xl border-2 border-orange-200 bg-white px-8 py-8 shadow-lg hover:shadow-xl hover:border-orange-400 transition-all duration-300"
              >
                <div className="text-4xl mb-3">🛠️</div>
                <h3 className="text-xl font-bold text-gray-900 group-hover:text-orange-600 transition-colors">
                  Admin
                </h3>
                <p className="text-sm text-gray-500 mt-2">
                  Upload &amp; manage rater workbooks
                </p>
              </button>

              {/* Client button */}
              <button
                onClick={() => onSelectPathway("client")}
                className="group w-64 rounded-2xl border-2 border-blue-200 bg-white px-8 py-8 shadow-lg hover:shadow-xl hover:border-blue-400 transition-all duration-300"
              >
                <div className="text-4xl mb-3">📊</div>
                <h3 className="text-xl font-bold text-gray-900 group-hover:text-blue-600 transition-colors">
                  Client
                </h3>
                <p className="text-sm text-gray-500 mt-2">
                  Calculate premiums with existing raters
                </p>
              </button>
            </div>
            <div className="mt-8 pt-4">
              <a
                href="/gateway/home"
                className="text-sm text-gray-400 hover:text-gray-600 underline underline-offset-4 transition-colors"
              >
                Return to Gateway Home
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
