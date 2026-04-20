"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import { apiGet, apiPost, apiUploadFormData } from "@/lib/api-client";
import { getWarmStateLabel, getWarmToneClass } from "@/lib/warm-status";
import { DynamicForm } from "@/components/tester/DynamicForm";
import { OutputPanel } from "@/components/tester/OutputPanel";
import type {
  RaterConfig,
  SourceType,
  AdminUploadResponse,
  AdminCalculateResponse,
  WarmState,
  WarmStatusResponse,
} from "@/types/rater";

export default function AdminPage() {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [config, setConfig] = useState<RaterConfig | null>(null);
  const [testInputs, setTestInputs] = useState<Record<string, unknown>>({});
  const [testOutputs, setTestOutputs] = useState<Record<string, string | number | null> | null>(null);
  const [saveSlug, setSaveSlug] = useState("");
  const [saveName, setSaveName] = useState("");
  const [saveDescription, setSaveDescription] = useState("");
  const [saveSource, setSaveSource] = useState<SourceType>("raters");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [warmState, setWarmState] = useState<WarmState | null>(null);
  const [warmDetail, setWarmDetail] = useState<string | null>(null);
  const [warmUsedLast, setWarmUsedLast] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!uploadId || warmState !== "warming") return;

    let active = true;
    const pollWarmStatus = async () => {
      try {
        const status = await apiGet<WarmStatusResponse>(`/api/admin/warm-status/${uploadId}`);
        if (!active) return;

        setWarmState(status.state);
        setWarmDetail(status.error || (status.active_operation ? `active: ${status.active_operation}` : null));
      } catch (err) {
        if (!active) return;
        const message = err instanceof Error ? err.message : String(err);
        setWarmState("unknown");
        setWarmDetail(message);
      }
    };

    pollWarmStatus();
    const timer = window.setInterval(pollWarmStatus, 1500);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [uploadId, warmState]);

  // Step 1: Upload & Parse
  const handleUpload = useCallback(async () => {
    if (!uploadedFile) {
      setError("Please select a file first");
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    const formData = new FormData();
    formData.append("file", uploadedFile);

    try {
      const data = await apiUploadFormData<AdminUploadResponse>("/api/admin/upload", formData);

      setUploadId(data.upload_id);
      setConfig(data.config);
      setSaveSlug(data.config.slug || "");
      setSaveName(data.filename.replace(/\.xlsx?$/i, ""));
      setWarmState(data.warm?.state ?? data.warm_status ?? "unknown");
      setWarmDetail(data.warm?.message ?? data.warm_message ?? null);
      setWarmUsedLast(null);
      setSuccess(
        `Parsed "${data.filename}" — ${data.config.inputs.length} inputs, ${data.config.outputs.length} outputs`
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Upload failed: ${message}`);
      setConfig(null);
      setWarmState(null);
      setWarmDetail(null);
      setWarmUsedLast(null);
    } finally {
      setLoading(false);
    }
  }, [uploadedFile]);

  // Step 2: Test Calculate
  const handleTestCalculate = useCallback(async () => {
    if (!uploadId || !config) {
      setError("No upload session active");
      return;
    }

    setTesting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await apiPost<AdminCalculateResponse>(
        "/api/admin/test-calculate",
        {
          upload_id: uploadId,
          inputs: testInputs,
        }
      );

      setTestOutputs(response.outputs);
      setWarmUsedLast(response.warm_used ?? null);
      if (response.warm_state) {
        setWarmState(response.warm_state);
      }

      if (response.warm_used === true) {
        setSuccess("Test calculation successful (warm path used)");
      } else if (response.warm_used === false) {
        setSuccess("Test calculation successful (cold fallback used)");
      } else {
        setSuccess("Test calculation successful");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Test calculate failed: ${message}`);
      setTestOutputs(null);
    } finally {
      setTesting(false);
    }
  }, [uploadId, config, testInputs]);

  // Step 3: Test Download
  const handleTestDownload = useCallback(async () => {
    if (!uploadId || !config) {
      setError("No upload session active");
      return;
    }

    setTesting(true);
    setError(null);
    setSuccess(null);

    try {
      const url = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/admin/test-download`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_id: uploadId,
          inputs: testInputs,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Download failed: ${response.status}`);
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = downloadUrl;
      a.download = `${config.slug || "test"}_calculated.xlsx`;
      a.click();
      window.URL.revokeObjectURL(downloadUrl);

      setSuccess("Test file downloaded successfully");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Test download failed: ${message}`);
    } finally {
      setTesting(false);
    }
  }, [uploadId, config, testInputs]);

  // Step 4: Save Rater
  const handleSave = useCallback(async () => {
    if (!uploadId || !config || !saveName) {
      setError("Missing required fields (upload, config, name)");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const actualSlug = saveName.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
      const url = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/admin/save`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_id: uploadId,
          config: {
            ...config,
            slug: actualSlug,
            name: saveName
          },
          slug: actualSlug,
          name: saveName,
          description: saveName,
          source: "raters",
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Save failed: ${response.status}`);
      }

      setSuccess(
        `✓ Successfully saved to raters/${actualSlug}. Rater is now available for use.`
      );

      // Reset form after successful save
      setTimeout(() => {
        setUploadedFile(null);
        setUploadId(null);
        setConfig(null);
        setTestInputs({});
        setTestOutputs(null);
        setSaveSlug("");
        setSaveName("");
        setSaveDescription("");
        setSaveSource("raters");
        setWarmState(null);
        setWarmDetail(null);
        setWarmUsedLast(null);
      }, 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Save failed: ${message}`);
    } finally {
      setSaving(false);
    }
  }, [uploadId, config, saveName]);

  const warmStateLabel = getWarmStateLabel(warmState);
  const warmToneClass = getWarmToneClass(warmState);

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      {/* Header */}
      <header className="mb-8 rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">
              Cogitate Excel Rater - Admin
            </h1>
            <p className="mt-2 text-slate-600">
              Upload Excel, review mappings, test outputs, approve rater
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Link
              href="/"
              className="rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
            >
              Back
            </Link>
          </div>
        </div>
      </header>

      {/* Alert Messages */}
      {error && (
        <div className="mb-6 rounded-md bg-red-50 p-4 text-sm text-red-900 border border-red-200">
          ✕ {error}
        </div>
      )}
      {success && (
        <div className="mb-6 rounded-md bg-green-50 p-4 text-sm text-green-900 border border-green-200">
          ✓ {success}
        </div>
      )}

      {/* Step 1: Upload */}
      <section className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-6 flex items-center gap-4 border-b pb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white font-bold">
            1
          </div>
          <h2 className="text-xl font-semibold text-slate-900">Upload Excel</h2>
        </div>
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Excel must contain a <code className="bg-gray-100 px-2 py-1 rounded">_Schema</code> sheet
            declaring inputs and outputs.
          </p>
          <div className="flex flex-wrap gap-3">
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => setUploadedFile(e.target.files?.[0] || null)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <button
              onClick={handleUpload}
              disabled={loading || !uploadedFile}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-400"
            >
              {loading ? "Uploading..." : "Upload & Parse"}
            </button>
          </div>
          {uploadedFile && (
            <p className="text-sm text-slate-600">
              Selected: <code className="bg-gray-100 px-2 py-1 rounded">{uploadedFile.name}</code>
            </p>
          )}

          {uploadId && warmStateLabel && (
            <div className={`rounded-md border px-3 py-2 text-sm ${warmToneClass}`}>
              <p className="font-medium">{warmStateLabel}</p>
              {warmDetail && <p className="mt-1 text-xs">{warmDetail}</p>}
              {warmUsedLast !== null && (
                <p className="mt-1 text-xs">
                  Last test path: {warmUsedLast ? "Warm" : "Cold fallback"}
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Step 2: Review */}
      {config && (
        <section className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-6 flex items-center gap-4 border-b pb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white font-bold">
              2
            </div>
            <h2 className="text-xl font-semibold text-slate-900">Review Configuration</h2>
          </div>
          <p className="mb-4 text-sm text-slate-600">
            {config.inputs.length} inputs, {config.outputs.length} outputs
          </p>

          {/* Inputs Table */}
          <div className="mb-6">
            <h3 className="mb-3 font-semibold text-slate-900">Inputs</h3>
            <div className="overflow-x-auto rounded-lg border border-gray-300">
              <table className="w-full border-collapse text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Field
                    </th>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Cell
                    </th>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Type
                    </th>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Label
                    </th>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Group
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {config.inputs.map((inp) => (
                    <tr key={inp.field} className="hover:bg-gray-50">
                      <td className="border border-gray-300 px-3 py-2">{inp.field}</td>
                      <td className="border border-gray-300 px-3 py-2">
                        <code className="bg-gray-100 px-1 py-0.5 rounded">{inp.cell || "-"}</code>
                      </td>
                      <td className="border border-gray-300 px-3 py-2">{inp.type}</td>
                      <td className="border border-gray-300 px-3 py-2">{inp.label}</td>
                      <td className="border border-gray-300 px-3 py-2">{inp.group || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Outputs Table */}
          <div>
            <h3 className="mb-3 font-semibold text-slate-900">Outputs</h3>
            <div className="overflow-x-auto rounded-lg border border-gray-300">
              <table className="w-full border-collapse text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Field
                    </th>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Cell
                    </th>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Label
                    </th>
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold">
                      Primary
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {config.outputs.map((out) => (
                    <tr key={out.field} className="hover:bg-gray-50">
                      <td className="border border-gray-300 px-3 py-2">{out.field}</td>
                      <td className="border border-gray-300 px-3 py-2">
                        <code className="bg-gray-100 px-1 py-0.5 rounded">{out.cell || "-"}</code>
                      </td>
                      <td className="border border-gray-300 px-3 py-2">{out.label}</td>
                      <td className="border border-gray-300 px-3 py-2">
                        {out.primary ? "✓" : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* Step 3: Test Calculate */}
      {config && (
        <section className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-6 flex items-center gap-4 border-b pb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white font-bold">
              3
            </div>
            <h2 className="text-xl font-semibold text-slate-900">Test Calculate</h2>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Test Form */}
            <div className="lg:col-span-2">
              <h3 className="mb-4 font-semibold text-slate-900">Enter Test Values</h3>
              <DynamicForm config={config} onInputsChange={setTestInputs} />
            </div>

            {/* Test Results */}
            <div>
              <h3 className="mb-4 font-semibold text-slate-900">Test Results</h3>
              <OutputPanel config={config} outputs={testOutputs} />
              
              {/* Test Buttons */}
              <div className="mt-6 flex flex-wrap gap-3">
                <button
                  onClick={handleTestCalculate}
                  disabled={testing}
                  className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:bg-gray-400"
                >
                  {testing ? "Testing..." : "Test Calculate"}
                </button>
                <button
                  onClick={handleTestDownload}
                  disabled={testing}
                  className="rounded-md bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 disabled:bg-gray-400"
                >
                  {testing ? "Downloading..." : "Test Download"}
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Step 4: Save */}
      {config && (
        <section className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-6 flex items-center gap-4 border-b pb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white font-bold">
              4
            </div>
            <h2 className="text-xl font-semibold text-slate-900">Approve & Save</h2>
          </div>

          <div className="grid gap-4 sm:grid-cols-1 max-w-sm">
            {/* Name Input */}
            <div className="flex flex-col gap-2">
              <label htmlFor="name" className="text-sm font-medium text-slate-700">
                Save Name
              </label>
              <input
                id="name"
                type="text"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                placeholder="e.g., MPL Rater Demo"
                className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Save Button */}
          <div className="mt-6">
            <button
              onClick={handleSave}
              disabled={saving || !saveName}
              className="rounded-md bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-400"
            >
              {saving ? "Saving..." : "Save Rater"}
            </button>
          </div>
        </section>
      )}
    </main>
  );
}

