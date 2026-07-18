import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function AuthCallback() {
  const nav = useNavigate();
  const loc = useLocation();
  const { setUser } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const hash = loc.hash || window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      nav("/login", { replace: true });
      return;
    }
    const session_id = decodeURIComponent(match[1]);
    (async () => {
      try {
        const { data } = await api.post("/auth/google/exchange", { session_id });
        if (data.token) localStorage.setItem("pd_token", data.token);
        setUser(data.user);
        toast.success(`Selamat datang, ${data.user.name}!`);
        // Clean fragment and redirect
        window.history.replaceState(null, "", window.location.pathname);
        nav(data.user.role === "admin" ? "/admin" : "/dashboard", { replace: true });
      } catch (e) {
        toast.error("Login Google gagal. Coba lagi.");
        nav("/login", { replace: true });
      }
    })();
  }, [loc, nav, setUser]);

  return (
    <div className="p-16 text-center">
      <div className="font-display text-3xl">Menghubungkan akun Google...</div>
      <div className="mt-2 text-gray-600">Sebentar ya, jangan tutup halaman ini.</div>
    </div>
  );
}
