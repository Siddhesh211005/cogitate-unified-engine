"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, Play, Calculator } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api-client";
import { DynamicForm } from "@/components/tester/DynamicForm";
import { OutputPanel } from "@/components/tester/OutputPanel";
import type { RaterConfig } from "@/types/rater";

export default function ClientPage() {
  const [raters, setRaters] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<{type: "raters" | "templates", id: string} | null>(null);
  const [config, setConfig] = useState<RaterConfig | null>(null);
  const [outputs, setOutputs] = useState<Record<string, string | number | null> | null>(null);
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [calculating, setCalculating] = useState(false);

  useEffect(() => {
    async function loadModels() {
      try {
        const [rRes, tRes] = await Promise.all([
          apiGet<any[]>("/api/raters"),
          apiGet<any[]>("/api/templates")
        ]);
        setRaters(rRes || []);
        setTemplates(tRes || []);
      } catch (err) {}
    }
    loadModels();
  }, []);

  const handleSelect = async (type: "raters" | "templates", recId: string) => {
    setSelectedRecord(recId ? { type, id: recId } : null);
    setConfig(null);
    setOutputs(null);
    if (!recId) return;
    try {
      const res = await apiGet<RaterConfig>(`/api/${type}/${recId}/config`);
      setConfig(res);
      const defaults: Record<string, any> = {};
      res.inputs?.forEach(inp => {
        if (inp.default !== undefined) defaults[inp.field] = inp.default;
      });
      setInputs(defaults);
    } catch (err) {}
  };

  const handleCalculate = async () => {
    if (!selectedRecord || !config) return;
    setCalculating(true);
    setOutputs(null);
    try {
      const res = await apiPost<{status: string, outputs: any}>(`/api/${selectedRecord.type}/${selectedRecord.id}/calculate`, inputs);
      setOutputs(res.outputs);
    } catch (err) {}
    setCalculating(false);
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 pb-12">
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-slate-400 hover:text-orange-600 transition">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-xl font-bold text-slate-800 flex items-center gap-2">
              <Calculator className="w-5 h-5 text-orange-600" /> Client Execution Panel
            </h1>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 mb-8">
          <label className="block text-sm font-semibold text-slate-900 mb-2">Select Active Rating Record</label>
          <select 
            className="w-full max-w-md rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={selectedRecord ? `${selectedRecord.type}|${selectedRecord.id}` : ""}
              onChange={(e) => {
                const val = e.target.value;
                if (!val) {
                  handleSelect("raters", ""); // type won't matter for clear
                  return;
                }
                const [targetType, targetId] = val.split("|");
                handleSelect(targetType as "raters" | "templates", targetId);
              }}
            >
              <option value="">-- Choose a Pricing Model --</option>
              <optgroup label="Saved Raters">
                {raters.map(r => (
                  <option key={`raters|${r.slug}`} value={`raters|${r.slug}`}>{r.name} ({r.slug})</option>
                ))}
              </optgroup>
              <optgroup label="System Templates">
                {templates.map(t => (
                  <option key={`templates|${t.slug}`} value={`templates|${t.slug}`}>{t.name} ({t.slug})</option>
                ))}
              </optgroup>
            </select>
          </div>

          {config && (
            <section className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <div className="grid gap-6 lg:grid-cols-3">
                {/* Test Form */}
                <div className="lg:col-span-2">
                  <h3 className="mb-4 font-semibold text-slate-900">Enter Test Values</h3>
                  <DynamicForm config={config} onInputsChange={setInputs} />
                </div>

                {/* Test Results */}
                <div>
                  <h3 className="mb-4 font-semibold text-slate-900">Test Results</h3>
                  <OutputPanel config={config} outputs={outputs} />

                  <div className="mt-6 flex flex-wrap gap-3">
                    <button
                      onClick={handleCalculate}
                      disabled={calculating}
                      className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:bg-gray-400"
                    >
                      {calculating ? "Executing..." : "Compute Premium"}
                    </button>
                  </div>
                </div>
              </div>
            </section>
        )}
      </div>
    </div>
  );
}
