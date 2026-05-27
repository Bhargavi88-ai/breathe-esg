import { useState, useEffect, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { uploadFile, getBatches } from "../api/client";
import toast from "react-hot-toast";

const SOURCE_OPTIONS = [
  { value: "sap", label: "SAP Export", desc: "MSEG flat-file extract (tab/semicolon/comma delimited)", accepts: ".csv,.txt,.tsv" },
  { value: "utility", label: "Utility Portal CSV", desc: "BESCOM / PG&E / British Gas billing history export", accepts: ".csv" },
  { value: "travel", label: "Corporate Travel", desc: "Concur / Navan expense report export", accepts: ".csv,.xlsx" },
];

const STATUS_STYLE = {
  pending: { color: "var(--text-muted)", icon: "○" },
  processing: { color: "var(--blue)", icon: "◌" },
  done: { color: "var(--green)", icon: "✓" },
  failed: { color: "var(--red)", icon: "✗" },
};

function BatchCard({ batch }) {
  const s = STATUS_STYLE[batch.status] || STATUS_STYLE.pending;
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "3px" }}>
            {batch.source_type_display}
          </div>
          <div style={{ fontSize: "13px", color: "var(--text)", wordBreak: "break-all" }}>{batch.original_filename}</div>
        </div>
        <span style={{ color: s.color, fontSize: "13px", fontWeight: "600", display: "flex", alignItems: "center", gap: "5px", flexShrink: 0, marginLeft: "12px" }}>
          {s.icon} {batch.status_display}
        </span>
      </div>
      <div style={{ display: "flex", gap: "16px", fontSize: "12px", color: "var(--text-muted)" }}>
        <span style={{ color: "var(--green)" }}>✓ {batch.rows_success} ingested</span>
        {batch.rows_failed > 0 && <span style={{ color: "var(--red)" }}>✗ {batch.rows_failed} failed</span>}
        {batch.rows_duplicate > 0 && <span style={{ color: "var(--text-dim)" }}>⊘ {batch.rows_duplicate} duplicate</span>}
        <span style={{ marginLeft: "auto" }}>{new Date(batch.created_at).toLocaleString()}</span>
      </div>

      {batch.error_message && (
        <div style={{ marginTop: "10px", padding: "8px 12px", background: "var(--red-dim)", border: "1px solid var(--red)44", borderRadius: "var(--radius-sm)", fontSize: "12px", color: "var(--red)", fontFamily: "var(--font-mono)" }}>
          {batch.error_message}
        </div>
      )}

      {batch.errors?.length > 0 && (
        <details style={{ marginTop: "10px" }}>
          <summary style={{ fontSize: "12px", color: "var(--amber)", cursor: "pointer" }}>
            {batch.errors.length} row-level errors (click to expand)
          </summary>
          <div style={{ marginTop: "8px", maxHeight: "160px", overflow: "auto" }}>
            {batch.errors.map((e) => (
              <div key={e.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: "11px", fontFamily: "var(--font-mono)" }}>
                <span style={{ color: "var(--text-muted)" }}>Row {e.row_index ?? "?"}: </span>
                <span style={{ color: "var(--red)" }}>{e.error_message}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export default function IngestionPage() {
  const [sourceType, setSourceType] = useState("sap");
  const [countryCode, setCountryCode] = useState("IN");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [batches, setBatches] = useState([]);

  const selectedSource = SOURCE_OPTIONS.find((s) => s.value === sourceType);

  const fetchBatches = useCallback(async () => {
    try {
      const { data } = await getBatches();
      setBatches(data.results || data);
    } catch {}
  }, []);

  useEffect(() => { fetchBatches(); }, [fetchBatches]);

  const onDrop = useCallback((accepted) => {
    if (accepted.length) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: { "text/csv": [".csv"], "text/plain": [".txt", ".tsv"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
  });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("source_type", sourceType);
    fd.append("file", file);
    fd.append("country_code", countryCode);
    try {
      const { data } = await uploadFile(fd);
      toast.success(`Ingested: ${data.rows_success} records, ${data.rows_failed} failed`);
      setFile(null);
      fetchBatches();
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.file?.[0] || "Upload failed";
      toast.error(msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{ maxWidth: "760px" }}>
      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: "700", fontSize: "22px", marginBottom: "4px" }}>Ingest Data</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "13px" }}>Upload a file from any of the three supported sources.</p>
      </div>

      {/* Source selector */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
        {SOURCE_OPTIONS.map((s) => (
          <button
            key={s.value}
            onClick={() => setSourceType(s.value)}
            style={{
              flex: 1,
              padding: "12px",
              background: sourceType === s.value ? "var(--surface2)" : "var(--surface)",
              border: `1px solid ${sourceType === s.value ? "var(--teal)" : "var(--border)"}`,
              borderRadius: "var(--radius)",
              color: sourceType === s.value ? "var(--teal)" : "var(--text-muted)",
              textAlign: "left",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            <div style={{ fontWeight: "600", fontSize: "13px", marginBottom: "3px" }}>{s.label}</div>
            <div style={{ fontSize: "11px", color: "var(--text-dim)", lineHeight: 1.4 }}>{s.desc}</div>
          </button>
        ))}
      </div>

      {/* Country selector for utility */}
      {sourceType === "utility" && (
        <div style={{ marginBottom: "16px" }}>
          <label style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: "6px" }}>
            Grid Region (affects emission factor)
          </label>
          <select value={countryCode} onChange={(e) => setCountryCode(e.target.value)} style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text)", padding: "8px 12px", fontSize: "13px" }}>
            <option value="IN">India (CEA 2022-23 — 0.708 kgCO₂e/kWh)</option>
            <option value="GB">United Kingdom (DEFRA 2023 — 0.212 kgCO₂e/kWh)</option>
            <option value="US">United States (EPA 2023 — 0.386 kgCO₂e/kWh)</option>
          </select>
        </div>
      )}

      {/* Dropzone */}
      <div
        {...getRootProps()}
        style={{
          border: `2px dashed ${isDragActive ? "var(--teal)" : file ? "var(--green)" : "var(--border2)"}`,
          borderRadius: "var(--radius)",
          padding: "36px",
          textAlign: "center",
          cursor: "pointer",
          background: isDragActive ? "var(--surface2)" : "var(--surface)",
          transition: "all 0.2s",
          marginBottom: "16px",
        }}
      >
        <input {...getInputProps()} />
        {file ? (
          <div>
            <div style={{ fontSize: "28px", marginBottom: "8px" }}>📄</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "13px", color: "var(--green)" }}>{file.name}</div>
            <div style={{ fontSize: "12px", color: "var(--text-dim)", marginTop: "4px" }}>
              {(file.size / 1024).toFixed(1)} KB
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); setFile(null); }}
              style={{ marginTop: "8px", background: "none", border: "none", color: "var(--text-dim)", fontSize: "12px", cursor: "pointer" }}
            >
              Remove
            </button>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: "32px", marginBottom: "8px" }}>↑</div>
            <div style={{ fontSize: "14px", fontWeight: "500", marginBottom: "4px" }}>
              {isDragActive ? "Drop to upload" : "Drop file here or click to browse"}
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              Accepts: {selectedSource?.accepts}
            </div>
          </div>
        )}
      </div>

      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        style={{
          width: "100%",
          padding: "12px",
          background: file ? "var(--teal)" : "var(--surface2)",
          border: "none",
          borderRadius: "var(--radius)",
          color: file ? "#000" : "var(--text-dim)",
          fontWeight: "600",
          fontSize: "14px",
          fontFamily: "var(--font-display)",
          cursor: file ? "pointer" : "not-allowed",
          marginBottom: "40px",
          transition: "all 0.15s",
        }}
      >
        {uploading ? "Processing…" : "Upload & Ingest"}
      </button>

      {/* Batch history */}
      <div>
        <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "14px" }}>
          Recent Batches
        </div>
        {batches.length === 0 ? (
          <div style={{ color: "var(--text-dim)", fontSize: "13px" }}>No ingestion batches yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {batches.slice(0, 10).map((b) => <BatchCard key={b.id} batch={b} />)}
          </div>
        )}
      </div>
    </div>
  );
}
