import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import toast from "react-hot-toast";

const NAV = [
  { to: "/", label: "Dashboard", icon: "◈" },
  { to: "/review", label: "Review", icon: "⊞" },
  { to: "/ingest", label: "Ingest", icon: "↑" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    toast.success("Signed out");
    navigate("/login");
  };

  return (
    <div style={styles.shell}>
      <aside style={styles.sidebar}>
        <div style={styles.brand}>
          <span style={styles.brandMark}>B</span>
          <div>
            <div style={styles.brandName}>Breathe ESG</div>
            <div style={styles.brandSub}>{user?.organisation?.name || "—"}</div>
          </div>
        </div>

        <nav style={styles.nav}>
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              style={({ isActive }) => ({
                ...styles.navItem,
                ...(isActive ? styles.navActive : {}),
              })}
            >
              <span style={styles.navIcon}>{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div style={styles.userBlock}>
          <div style={styles.userInfo}>
            <div style={styles.userAvatar}>{user?.email?.[0]?.toUpperCase()}</div>
            <div>
              <div style={styles.userName}>{user?.first_name || user?.email}</div>
              <div style={styles.userRole}>{user?.role}</div>
            </div>
          </div>
          <button onClick={handleLogout} style={styles.logoutBtn}>Sign out</button>
        </div>
      </aside>

      <main style={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}

const styles = {
  shell: { display: "flex", minHeight: "100vh", background: "var(--bg)" },
  sidebar: {
    width: "220px",
    flexShrink: 0,
    background: "var(--surface)",
    borderRight: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    padding: "20px 0",
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "0 20px 24px",
    borderBottom: "1px solid var(--border)",
  },
  brandMark: {
    width: "30px",
    height: "30px",
    background: "var(--teal)",
    borderRadius: "7px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--font-display)",
    fontWeight: "700",
    fontSize: "16px",
    color: "#000",
    flexShrink: 0,
  },
  brandName: { fontFamily: "var(--font-display)", fontWeight: "600", fontSize: "14px" },
  brandSub: { fontSize: "11px", color: "var(--text-muted)", marginTop: "1px" },
  nav: { flex: 1, padding: "16px 10px", display: "flex", flexDirection: "column", gap: "2px" },
  navItem: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "8px 10px",
    borderRadius: "var(--radius)",
    color: "var(--text-muted)",
    fontSize: "13px",
    fontWeight: "500",
    transition: "all 0.15s",
    textDecoration: "none",
  },
  navActive: {
    background: "var(--surface2)",
    color: "var(--text)",
    borderLeft: "2px solid var(--teal)",
    paddingLeft: "8px",
  },
  navIcon: { fontSize: "14px", width: "16px", textAlign: "center" },
  userBlock: {
    padding: "16px 20px",
    borderTop: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  userInfo: { display: "flex", alignItems: "center", gap: "10px" },
  userAvatar: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    background: "var(--teal)",
    color: "#000",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: "700",
    fontSize: "13px",
  },
  userName: { fontSize: "12px", fontWeight: "500", color: "var(--text)" },
  userRole: { fontSize: "11px", color: "var(--text-muted)", textTransform: "capitalize" },
  logoutBtn: {
    background: "var(--surface2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-muted)",
    padding: "6px 10px",
    fontSize: "12px",
    cursor: "pointer",
    textAlign: "left",
    transition: "color 0.15s",
  },
  main: { flex: 1, overflow: "auto", padding: "32px" },
};
