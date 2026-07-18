import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

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
        </form>
      </div>
    </div>
  );
}
