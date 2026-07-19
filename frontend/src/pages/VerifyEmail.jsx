import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CheckCircle, XCircle, ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { setUser, setToken } = useAuth();
  const [status, setStatus] = useState("loading"); // loading | success | error
  const [message, setMessage] = useState("");
  const attempted = useRef(false);

  useEffect(() => {
    // Guard: StrictMode dev + email prefetchers (Gmail, corp scanners) can invoke this twice.
    // Backend is now idempotent, but we still guard here for cleaner UX.
    if (attempted.current) return;
    const token = params.get("token");
    if (!token) { setStatus("error"); setMessage("Token tidak ditemukan di URL."); return; }
    attempted.current = true;
    api.post("/auth/verify-email", { token })
      .then(({ data }) => {
        setStatus("success");
        setMessage("Email berhasil diverifikasi.");
        if (data?.token && data?.user) {
          localStorage.setItem("token", data.token);
          setToken(data.token); setUser(data.user);
          setTimeout(() => nav("/dashboard", { replace: true }), 1800);
        } else {
          setTimeout(() => nav("/login", { replace: true }), 1800);
        }
      })
      .catch((e) => { setStatus("error"); setMessage(formatApiError(e.response?.data?.detail) || "Gagal verifikasi."); });
  }, [params, nav, setUser, setToken]);

  return (
    <div className="min-h-[calc(100vh-73px)] flex items-center justify-center p-6">
      <div className="brutal p-10 md:p-14 max-w-lg text-center" data-testid="verify-email-page">
        {status === "loading" && (
          <>
            <div className="animate-pulse font-mono text-sm uppercase">Memverifikasi...</div>
          </>
        )}
        {status === "success" && (
          <>
            <CheckCircle weight="fill" size={64} className="text-[#34C759] mx-auto" />
            <h1 className="mt-4 font-display font-black text-3xl">Email diverifikasi!</h1>
            <p className="mt-2 text-gray-700">{message}</p>
            <div className="mt-6"><Link to="/dashboard" className="brutal-btn brutal-btn-red">Masuk ke Dashboard <ArrowRight weight="bold" /></Link></div>
          </>
        )}
        {status === "error" && (
          <>
            <XCircle weight="fill" size={64} className="text-[#FF3B30] mx-auto" />
            <h1 className="mt-4 font-display font-black text-3xl">Gagal verifikasi</h1>
            <p className="mt-2 text-gray-700">{message}</p>
            <div className="mt-6 space-y-2">
              <ResendForm />
              <Link to="/login" className="text-sm underline block mt-4">Kembali ke Login</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ResendForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/resend-verification", { email });
      toast.success("Jika email terdaftar, link verifikasi baru sudah dikirim.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="brutal-sm bg-[#FFD60A]/40 p-4 text-left" data-testid="resend-verification-form">
      <div className="font-mono text-xs uppercase mb-2">Minta ulang link verifikasi</div>
      <div className="flex gap-2">
        <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email kamu" className="brutal-input flex-1" data-testid="resend-email-input" />
        <button type="submit" disabled={busy} className="brutal-btn brutal-btn-red text-sm" data-testid="resend-submit">{busy ? "..." : "Kirim"}</button>
      </div>
    </form>
  );
}
