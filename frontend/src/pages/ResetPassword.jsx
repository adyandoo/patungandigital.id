import { useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const token = params.get("token") || "";
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw !== pw2) return toast.error("Konfirmasi password tidak cocok.");
    if (pw.length < 6) return toast.error("Password minimal 6 karakter.");
    if (!token) return toast.error("Token tidak ditemukan di URL.");
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: pw });
      setDone(true);
      setTimeout(() => nav("/login", { replace: true }), 2000);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-[calc(100vh-73px)] grid md:grid-cols-2">
      <div className="hidden md:block bg-[#FFD60A] border-r-2 border-black relative overflow-hidden">
        <div className="absolute inset-0 noise-grid opacity-30"></div>
        <div className="p-12 relative z-10">
          <div className="pd-tag bg-[#FF3B30] text-white">Reset</div>
          <h1 className="mt-6 font-display font-black text-6xl text-black leading-none">Set password<br />baru.</h1>
          <p className="mt-6 text-black/80 text-lg max-w-md">Aman & cepat. Setelah selesai kamu akan diarahkan ke halaman login.</p>
        </div>
      </div>
      <div className="p-8 md:p-16 flex items-center">
        <div className="w-full max-w-md" data-testid="reset-page">
          <h2 className="font-display font-black text-4xl">Reset Password</h2>
          {done ? (
            <div className="mt-6 brutal-sm bg-[#34C759]/30 p-4" data-testid="reset-done">
              Password berhasil di-reset. Mengarahkan ke halaman login...
            </div>
          ) : (
            <form onSubmit={submit} className="mt-8 space-y-4">
              <div>
                <label className="font-mono text-xs uppercase">Password baru</label>
                <input required type="password" value={pw} onChange={(e) => setPw(e.target.value)} className="brutal-input mt-2" minLength={6} data-testid="reset-pw" placeholder="min 6 karakter" />
              </div>
              <div>
                <label className="font-mono text-xs uppercase">Konfirmasi password</label>
                <input required type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} className="brutal-input mt-2" minLength={6} data-testid="reset-pw2" />
              </div>
              <button disabled={busy || !token} type="submit" className="brutal-btn brutal-btn-red w-full justify-center" data-testid="reset-submit">
                {busy ? "Menyimpan..." : "Simpan password baru"}
              </button>
              {!token && <p className="text-sm text-red-700">Token reset tidak ditemukan di URL. Minta ulang dari halaman login.</p>}
              <p className="text-sm mt-3"><Link to="/login" className="underline">Kembali ke Login</Link></p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
