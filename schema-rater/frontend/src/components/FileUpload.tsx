import { useCallback, useState, type ChangeEvent } from "react";

interface Props {
  onUploaded: (raterId: string) => void;
}

export default function FileUpload({ onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const doUpload = useCallback(
    async (file: File) => {
      setError(null);
      setFileName(file.name);
      setUploading(true);
      try {
        const { uploadRater } = await import("../api");
        const resp = await uploadRater(file);
        onUploaded(resp.rater_id);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setUploading(false);
      }
    },
    [onUploaded],
  );

  const handleFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) doUpload(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) doUpload(file);
  };

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
        dragging
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 hover:border-gray-400"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <div className="space-y-3">
        <svg
          className="mx-auto h-12 w-12 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>

        <div>
          <label className="cursor-pointer text-blue-600 hover:text-blue-500 font-medium">
            Choose an Excel rater
            <input
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleFile}
              disabled={uploading}
            />
          </label>
          <span className="text-gray-500"> or drag and drop</span>
        </div>

        <p className="text-xs text-gray-400">.xlsx or .xls up to 50 MB</p>

        {uploading && (
          <p className="text-sm text-blue-600 animate-pulse">
            Uploading &amp; parsing {fileName}…
          </p>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </div>
  );
}
