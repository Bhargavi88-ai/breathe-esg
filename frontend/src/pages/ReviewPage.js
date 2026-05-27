import { useState, useEffect, useCallback } from "react";
import { getRecords, approveRecord, flagRecord, bulkApprove } from "../api/client";
import toast from "react-hot-toast";

const STATUS_STYLE = {
  pending: { color: "var(--amber)", bg: "var(--amber-dim)", label: "Pending" },
  approved: { color: "var(--green)", bg: "var(--green-dim)", label: "Approved" },
  flagged: { color: "var(--red)", bg: "var(--red-dim)", label: "Flagged" },
  locked: { color: "var(--text-dim)", bg: "var(--surface2)", label: "Locked" },
};

const SCOPE_COLOR = { "1": "var(--teal)", "2": "var(--blue)", "3": "var(--amber)" };

function Badge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.pending;
  return (
    <span style={{ background: s.bg, color: s.color, border: `1px solid ${s.color}44`, borderRadius: "4px", padding: "2px 8px", fontSize: "11px", fontWeight: "600", letterSpacing: "0.03em" }}>
      {s.label}
    </span>
  );
}

function ScopePill({ scope }) {
  return (
    <span style={{ color: SCOPE_COLOR[scope] || "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: "600" }}>
      S{scope}
    </span>
  );
}

function fmt(kg) {
  if (!kg) return "—";
  const n = parseFloat(kg);
  if (n >= 1000) return `${(n / 1000).toFixed(2)} tCO₂e`;
  return `${n.toFixed(2)} kgCO₂e`;
}

function FlagModal({ record, onClose, onFlag }) {
  const [note, setNote] = useState("");
  return (
    <div style={{ position: "fixed", inset: 0, background: "#00000088", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
      <div style={{ background: "var(--surface2)", border: "1px solid var(--border2)", borderRadius: "10px", padding: "24px", width: "400px", maxWidth: "90vw" }}>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: "600", fontSize: "15px", marginBottom: "8px" }}>Flag Record</div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "16px" }}>
          {record?.raw_description || record?.category_display}
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Describe the issue (e.g. duplicate entry, unit mismatch, missing data)…"
          style={{ width: "100%", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)", padding: "10px 12px", fontSize: "13px", minHeight: "80px", resize: "vertical", fontFamily: "var(--font-sans)" }}
          autoFocus
        />
        <div style={{ display: "flex", gap: "10px", marginTop: "16px", justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ padding: "8px 14px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-muted)", fontSize: "13px" }}>
            Cancel
          </button>
          <button onClick={() => onFlag(record.id, note)} style={{ padding: "8px 14px", background: "var(--red-dim)", border: "1px solid var(--red)", borderRadius: "var(--radius-sm)", color: "var(--red)", fontSize: "13px", fontWeight: "600" }}>
            Flag
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ReviewPage() {
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [flagTarget, setFlagTarget] = useState(null);
  const [filters, setFilters] = useState({ status: "pending", scope: "", source_type: "", search: "" });
  const [page, setPage] = useState(1);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) };
      const { data } = await getRecords(params);
      setRecords(data.results || []);
      setTotal(data.count || 0);
    } catch {
      toast.error("Failed to load records");
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  const handleApprove = async (id) => {
    try {
      await approveRecord(id);
      toast.success("Approved");
      fetchRecords();
    } catch { toast.error("Failed to approve"); }
  };

  const handleFlag = async (id, note) => {
    try {
      await flagRecord(id, note);
      toast.success("Flagged");
      setFlagTarget(null);
      fetchRecords();
    } catch { toast.error("Failed to flag"); }
  };

  const handleBulkApprove = async () => {
    if (!selected.size) return;
    try {
      const { data } = await bulkApprove([...selected]);
      toast.success(`Approved ${data.approved} records`);
      setSelected(new Set());
      fetchRecords();
    } catch { toast.error("Bulk approve failed"); }
  };

  const toggleSelect = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const toggleAll = () => {
    if (selected.size === records.length) setSelected(new Set());
    else setSelected(new Set(records.map((r) => r.id)));
  };

  const filterChange = (key, val) => {
    setFilters((f) => ({ ...f, [key]: val }));
    setPage(1);
  };

  const totalPages = Math.ceil(total / 50);

  return (
    <div>
      {flagTarget && (
        <FlagModal record={flagTarget} onClose={() => setFlagTarget(null)} onFlag={handleFlag} />
      )}

      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: "700", fontSize: "22px", marginBottom: "4px" }}>
          Review Queue
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "13px" }}>{total} records · page {page} of {totalPages || 1}</p>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "16px", flexWrap: "wrap" }}>
        <select value={filters.status} onChange={(e) => filterChange("status", e.target.value)} style={selStyle}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="flagged">Flagged</option>
          <option value="locked">Locked</option>
        </select>
        <select value={filters.scope} onChange={(e) => filterChange("scope", e.target.value)} style={selStyle}>
          <option value="">All scopes</option>
          <option value="1">Scope 1</option>
          <option value="2">Scope 2</option>
          <option value="3">Scope 3</option>
        </select>
        <select value={filters.source_type} onChange={(e) => filterChange("source_type", e.target.value)} style={selStyle}>
          <option value="">All sources</option>
          <option value="sap">SAP</option>
          <option value="utility">Utility</option>
          <option value="travel">Travel</option>
        </select>
        <input
          value={filters.search}
          onChange={(e) => filterChange("search", e.target.value)}
          placeholder="Search description, facility…"
          style={{ ...selStyle, minWidth: "220px" }}
        />

        {selected.size > 0 && (
          <button onClick={handleBulkApprove} style={{ marginLeft: "auto", background: "var(--green-dim)", border: "1px solid var(--green)", borderRadius: "var(--radius-sm)", color: "var(--green)", padding: "8px 14px", fontSize: "13px", fontWeight: "600" }}>
            ✓ Approve {selected.size} selected
          </button>
        )}
      </div>

      {/* Table */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th style={th}><input type="checkbox" onChange={toggleAll} checked={selected.size === records.length && records.length > 0} style={{ accentColor: "var(--teal)" }} /></th>
              <th style={th}>Date</th>
              <th style={th}>Source</th>
              <th style={th}>Scope</th>
              <th style={th}>Category</th>
              <th style={th}>Description</th>
              <th style={th}>Facility</th>
              <th style={{ ...th, textAlign: "right" }}>kgCO₂e</th>
              <th style={th}>Status</th>
              <th style={th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={10} style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>Loading…</td></tr>
            ) : records.length === 0 ? (
              <tr><td colSpan={10} style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>No records match your filters.</td></tr>
            ) : records.map((r) => (
              <tr key={r.id} style={{ borderBottom: "1px solid var(--border)", background: selected.has(r.id) ? "var(--surface2)" : "transparent" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = selected.has(r.id) ? "var(--surface2)" : "#ffffff06"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = selected.has(r.id) ? "var(--surface2)" : "transparent"; }}
              >
                <td style={td}><input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} style={{ accentColor: "var(--teal)" }} /></td>
                <td style={{ ...td, fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-muted)" }}>
                  {r.activity_date || "—"}
                </td>
                <td style={{ ...td, fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase" }}>
                  {r.source_type}
                </td>
                <td style={td}><ScopePill scope={r.scope} /></td>
                <td style={{ ...td, fontSize: "12px", color: "var(--text-muted)" }}>{r.category_display}</td>
                <td style={{ ...td, maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "12px" }}>
                  {r.raw_description || r.sub_category || "—"}
                </td>
                <td style={{ ...td, fontSize: "12px", color: "var(--text-muted)" }}>{r.facility_name || r.facility_code || "—"}</td>
                <td style={{ ...td, textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
                  {r.kg_co2e ? parseFloat(r.kg_co2e).toFixed(2) : "—"}
                </td>
                <td style={td}><Badge status={r.status} /></td>
                <td style={td}>
                  <div style={{ display: "flex", gap: "6px" }}>
                    {r.status !== "approved" && r.status !== "locked" && (
                      <button onClick={() => handleApprove(r.id)} style={btnGreen}>✓</button>
                    )}
                    {r.status !== "locked" && (
                      <button onClick={() => setFlagTarget(r)} style={btnRed}>⚑</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", gap: "8px", marginTop: "16px", justifyContent: "center" }}>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} style={pagBtn}>← Prev</button>
          <span style={{ color: "var(--text-muted)", padding: "6px 12px", fontSize: "13px" }}>{page} / {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} style={pagBtn}>Next →</button>
        </div>
      )}
    </div>
  );
}

const selStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text)",
  padding: "8px 10px",
  fontSize: "13px",
  outline: "none",
};

const th = {
  padding: "10px 14px",
  textAlign: "left",
  fontSize: "11px",
  fontWeight: "600",
  color: "var(--text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  background: "var(--surface)",
  whiteSpace: "nowrap",
};

const td = { padding: "10px 14px" };

const btnGreen = {
  background: "var(--green-dim)",
  border: "1px solid var(--green)",
  borderRadius: "4px",
  color: "var(--green)",
  padding: "4px 8px",
  fontSize: "12px",
  cursor: "pointer",
};

const btnRed = {
  background: "var(--red-dim)",
  border: "1px solid var(--red)",
  borderRadius: "4px",
  color: "var(--red)",
  padding: "4px 8px",
  fontSize: "12px",
  cursor: "pointer",
};

const pagBtn = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text-muted)",
  padding: "6px 14px",
  fontSize: "13px",
  cursor: "pointer",
};
