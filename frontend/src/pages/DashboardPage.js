import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from "recharts";
import { getSummary } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { Link } from "react-router-dom";

const SCOPE_COLORS = { "1": "#14b8a6", "2": "#3b82f6", "3": "#f59e0b" };
const SOURCE_COLORS = { sap: "#14b8a6", utility: "#3b82f6", travel: "#f59e0b" };

function MetricCard({ label, value, sub, color }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "20px", borderTop: `2px solid ${color || "var(--border)"}` }}>
      <div style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: "28px", fontWeight: "700", color: "var(--text)", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "6px" }}>{sub}</div>}
    </div>
  );
}

function StatusPill({ count, label, color }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
      <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "13px" }}>{count}</span>
      <span style={{ color: "var(--text-muted)", fontSize: "12px" }}>{label}</span>
    </div>
  );
}

function tCO2e(kg) {
  if (!kg) return "—";
  const t = parseFloat(kg) / 1000;
  if (t >= 1000) return `${(t / 1000).toFixed(1)}k tCO₂e`;
  return `${t.toFixed(1)} tCO₂e`;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSummary()
      .then((r) => setSummary(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--text-muted)", padding: "40px" }}>Loading…</div>;
  if (!summary) return <div style={{ color: "var(--red)", padding: "40px" }}>Failed to load summary.</div>;

  const totalT = parseFloat(summary.total_kg_co2e) / 1000;
  const pieData = summary.by_scope.map((s) => ({
    name: `Scope ${s.scope}`,
    value: parseFloat(s.total_kg_co2e) / 1000,
    color: SCOPE_COLORS[s.scope],
  }));

  const barData = summary.by_source.map((s) => ({
    name: s.label,
    tCO2e: parseFloat(s.total_kg_co2e) / 1000,
    color: SOURCE_COLORS[s.source] || "#6b7280",
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "28px" }}>
        <div>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: "700", fontSize: "22px", marginBottom: "4px" }}>
            Emissions Dashboard
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "13px" }}>
            {user?.organisation?.name} · Reporting year {user?.organisation?.active_reporting_year}
          </p>
        </div>
        {summary.pending_count > 0 && (
          <Link to="/review" style={{ background: "var(--amber-dim)", border: "1px solid var(--amber)", borderRadius: "var(--radius)", padding: "8px 16px", color: "var(--amber)", fontSize: "13px", fontWeight: "600", textDecoration: "none" }}>
            ⚠ {summary.pending_count} pending review
          </Link>
        )}
      </div>

      {/* KPI row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px", marginBottom: "24px" }}>
        <MetricCard label="Total Emissions" value={tCO2e(summary.total_kg_co2e * 1000)} color="var(--teal)" />
        {summary.by_scope.map((s) => (
          <MetricCard
            key={s.scope}
            label={s.scope_display}
            value={tCO2e(s.total_kg_co2e * 1000)}
            sub={`${s.record_count} records`}
            color={SCOPE_COLORS[s.scope]}
          />
        ))}
      </div>

      {/* Review status */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "20px", marginBottom: "24px" }}>
        <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "16px" }}>Review Status by Scope</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0" }}>
          {summary.by_scope.map((s, i) => (
            <div key={s.scope} style={{ padding: "12px 20px", borderRight: i < 2 ? "1px solid var(--border)" : "none" }}>
              <div style={{ fontSize: "12px", fontWeight: "600", color: SCOPE_COLORS[s.scope], marginBottom: "10px" }}>{s.scope_display}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <StatusPill count={s.pending_count} label="pending" color="var(--amber)" />
                <StatusPill count={s.approved_count} label="approved" color="var(--green)" />
                <StatusPill count={s.flagged_count} label="flagged" color="var(--red)" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "20px" }}>
          <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "16px" }}>Emissions by Source (tCO₂e)</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={barData} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
              <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "6px", fontSize: "12px" }} cursor={{ fill: "var(--surface2)" }} />
              <Bar dataKey="tCO2e" radius={[4, 4, 0, 0]}>
                {barData.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "20px" }}>
          <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "16px" }}>Scope Split</div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={3}>
                {pieData.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
              <Tooltip formatter={(v) => `${v.toFixed(1)} tCO₂e`} contentStyle={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "6px", fontSize: "12px" }} />
              <Legend formatter={(v) => <span style={{ color: "var(--text-muted)", fontSize: "12px" }}>{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
