import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import toast from "react-hot-toast";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      toast.error("Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <div style={styles.logo}>
          <span style={styles.logoMark}>B</span>
          <span style={styles.logoText}>Breathe ESG</span>
        </div>
        <p style={styles.tagline}>Emissions data ingestion & review platform</p>

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label style={styles.label}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
              placeholder="analyst@company.com"
              required
              autoFocus
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={styles.input}
              placeholder="••••••••"
              required
            />
          </div>
          <button type="submit" disabled={loading} style={styles.btn}>
            {loading ? "Signing in…" : "Sign in →"}
          </button>
        </form>

        <div style={styles.demoBox}>
          <p style={styles.demoTitle}>Demo credentials</p>
          <div style={styles.demoRow}>
            <span style={styles.mono}>admin@acme.com</span>
            <span style={styles.mono}>demo1234</span>
          </div>
          <div style={styles.demoRow}>
            <span style={styles.mono}>analyst@acme.com</span>
            <span style={styles.mono}>demo1234</span>
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "var(--bg)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "24px",
  },
  card: {
    width: "100%",
    maxWidth: "400px",
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "12px",
    padding: "40px",
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    marginBottom: "8px",
  },
  logoMark: {
    width: "32px",
    height: "32px",
    background: "var(--teal)",
    borderRadius: "8px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--font-display)",
    fontWeight: "700",
    fontSize: "18px",
    color: "#000",
  },
  logoText: {
    fontFamily: "var(--font-display)",
    fontWeight: "600",
    fontSize: "18px",
    color: "var(--text)",
  },
  tagline: {
    color: "var(--text-muted)",
    fontSize: "13px",
    marginBottom: "32px",
  },
  form: { display: "flex", flexDirection: "column", gap: "16px" },
  field: { display: "flex", flexDirection: "column", gap: "6px" },
  label: { fontSize: "12px", fontWeight: "500", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" },
  input: {
    background: "var(--surface2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    color: "var(--text)",
    padding: "10px 12px",
    fontSize: "14px",
    outline: "none",
    transition: "border-color 0.15s",
  },
  btn: {
    background: "var(--teal)",
    color: "#000",
    border: "none",
    borderRadius: "var(--radius)",
    padding: "12px",
    fontWeight: "600",
    fontSize: "14px",
    fontFamily: "var(--font-display)",
    marginTop: "8px",
    transition: "opacity 0.15s",
  },
  demoBox: {
    marginTop: "32px",
    padding: "16px",
    background: "var(--surface2)",
    borderRadius: "var(--radius)",
    border: "1px solid var(--border)",
  },
  demoTitle: {
    fontSize: "11px",
    fontWeight: "600",
    color: "var(--text-dim)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    marginBottom: "8px",
  },
  demoRow: {
    display: "flex",
    justifyContent: "space-between",
    padding: "4px 0",
    borderBottom: "1px solid var(--border)",
  },
  mono: { fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-muted)" },
};
