import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [showForgot, setShowForgot] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const u = await login(email, password);
      toast.success("Selamat datang kembali!");
      nav(u.role === "admin" ? "/admin" : "/dashboard");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-73px)] grid md:grid-cols-2">
      <div className="hidden md:block bg-[#FF3B30] border-r-2 border-black relative overflow-hidden">
        <div className="absolute inset-0 noise-grid opacity-30"></div>
        <div className="p-12 relative z-10">
          <div className="pd-tag bg-[#FFD60A]">Masuk</div>
          <h1 className="mt-6 font-display font-black text-6xl text-white leading-none">Balik lagi ke patungan.</h1>
          <p className="mt-6 text-white/90 text-lg max-w-md">Cek langganan aktif, riwayat bayar, dan pengingat tagihanmu.</p>
        </div>
      </div>
      <div className="p-8 md:p-16 flex items-center">
        <form onSubmit={submit} className="w-full max-w-md" data-testid="login-form">
          <h2 className="font-display font-black text-4xl">Masuk</h2>
          <p className="text-gray-700 mt-2">Belum punya akun? <Link to="/register" className="underline font-semibold">Daftar</Link></p>
          <div className="mt-8 space-y-4">
            <div>
              <label className="font-mono text-xs uppercase">Email</label>
              <input data-testid="login-email" required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="brutal-input mt-2" placeholder="kamu@email.com" />
            </div>
            <div>
              <label className="font-mono text-xs uppercase">Password</label>
              <input data-testid="login-password" required type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="brutal-input mt-2" placeholder="••••••••" />
            </div>
          </div>
          <button disabled={loading} type="submit" data-testid="login-submit" className="brutal-btn brutal-btn-red w-full justify-center mt-8">
            {loading ? "Memproses..." : "Masuk"}
          </button>
          <div className="mt-3 text-right">
            <button type="button" onClick={() => setShowForgot(true)} className="text-sm underline font-mono" data-testid="forgot-password-link">
              Lupa password?
            </button>
          </div>
          <div className="my-6 flex items-center gap-3">
            <div className="flex-1 h-[2px] bg-black"></div>
            <span className="font-mono text-xs uppercase">atau</span>
            <div className="flex-1 h-[2px] bg-black"></div>
          </div>
          <button
            type="button"
            data-testid="login-google"
            onClick={() => {
              // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
              const redirectUrl = window.location.origin + "/dashboard";
              window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
            }}
            className="brutal-btn brutal-btn-white w-full justify-center"
          >
            <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
            Lanjut dengan Google
          </button>
        </form>
      </div>
      {showForgot && <ForgotModal defaultEmail={email} onClose={() => setShowForgot(false)} />}
    </div>
  );
}

function ForgotModal({ defaultEmail, onClose }) {
  const [email, setEmail] = useState(defaultEmail || "");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setDone(true);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="brutal-lg bg-white max-w-md w-full" onClick={(e) => e.stopPropagation()} data-testid="forgot-modal">
        <div className="border-b-2 border-black p-4 bg-[#FFD60A] flex items-center justify-between">
          <div className="font-display font-black text-xl">Reset Password</div>
          <button onClick={onClose} className="font-mono text-sm">Tutup</button>
        </div>
        <div className="p-6">
          {done ? (
            <div data-testid="forgot-done" className="space-y-3">
              <div className="brutal-sm bg-[#34C759]/30 p-4">
                Jika email <b>{email}</b> terdaftar, kami sudah mengirim link reset password. Cek inbox/spam. Link berlaku 1 jam.
              </div>
              <p className="text-sm text-gray-700">Tidak dapat email? Hubungi admin di WhatsApp untuk reset manual.</p>
              <button onClick={onClose} className="brutal-btn brutal-btn-red w-full justify-center">OK</button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-3">
              <p className="text-sm text-gray-700">Masukkan email akunmu. Kami akan kirim link reset password.</p>
              <input required type="email" className="brutal-input" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="kamu@email.com" data-testid="forgot-email" />
              <button type="submit" disabled={busy} className="brutal-btn brutal-btn-red w-full justify-center" data-testid="forgot-submit">
                {busy ? "Mengirim..." : "Kirim link reset"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
