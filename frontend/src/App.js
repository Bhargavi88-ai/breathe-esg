import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import ReviewPage from "./pages/ReviewPage";
import IngestionPage from "./pages/IngestionPage";
import Layout from "./components/Layout";

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:'100vh',color:'var(--text-muted)'}}>Loading…</div>;
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" toastOptions={{
          style: { background: 'var(--surface2)', color: 'var(--text)', border: '1px solid var(--border2)', fontFamily: 'var(--font-sans)', fontSize: '13px' },
          success: { iconTheme: { primary: 'var(--green)', secondary: 'var(--bg)' } },
          error: { iconTheme: { primary: 'var(--red)', secondary: 'var(--bg)' } },
        }} />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
            <Route index element={<DashboardPage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="ingest" element={<IngestionPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
