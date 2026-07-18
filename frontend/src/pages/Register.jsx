import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ name: "", username: "", email: "", password: "", whatsapp: "", gender: "" });
  const [loading, setLoading] = useState(false);

  const change = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(form);
      toast.success("Akun berhasil dibuat!");
      nav("/dashboard");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-73px)] grid md:grid-cols-2">
      <div className="p-8 md:p-16 order-2 md:order-1 flex items-center">
        <form onSubmit={submit} className="w-full max-w-md" data-testid="register-form">
          <h2 className="font-display font-black text-4xl">Daftar akun</h2>
          <p className="text-gray-700 mt-2">Sudah punya? <Link to="/login" className="underline font-semibold">Masuk</Link></p>
          <div className="mt-8 grid grid-cols-1 gap-4">
            <div>
              <label className="font-mono text-xs uppercase">Nama lengkap</label>
              <input data-testid="reg-name" required value={form.name} onChange={change("name")} className="brutal-input mt-2" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="font-mono text-xs uppercase">Username</label>
                <input data-testid="reg-username" value={form.username} onChange={change("username")} className="brutal-input mt-2" />
              </div>
              <div>
                <label className="font-mono text-xs uppercase">Gender</label>
                <select data-testid="reg-gender" value={form.gender} onChange={change("gender")} className="brutal-input mt-2">
                  <option value="">Pilih...</option>
                  <option value="L">Laki-laki</option>
                  <option value="P">Perempuan</option>
                </select>
              </div>
            </div>
            <div>
              <label className="font-mono text-xs uppercase">Email</label>
              <input data-testid="reg-email" required type="email" value={form.email} onChange={change("email")} className="brutal-input mt-2" />
            </div>
            <div>
              <label className="font-mono text-xs uppercase">WhatsApp</label>
              <input data-testid="reg-whatsapp" value={form.whatsapp} onChange={change("whatsapp")} className="brutal-input mt-2" placeholder="+628xxx" />
            </div>
            <div>
              <label className="font-mono text-xs uppercase">Password</label>
              <input data-testid="reg-password" required type="password" minLength={6} value={form.password} onChange={change("password")} className="brutal-input mt-2" />
            </div>
          </div>
          <button disabled={loading} type="submit" data-testid="reg-submit" className="brutal-btn brutal-btn-red w-full justify-center mt-8">
            {loading ? "Memproses..." : "Buat akun"}
          </button>
          <div className="my-6 flex items-center gap-3">
            <div className="flex-1 h-[2px] bg-black"></div>
            <span className="font-mono text-xs uppercase">atau</span>
            <div className="flex-1 h-[2px] bg-black"></div>
          </div>
          <button
            type="button"
            data-testid="reg-google"
            onClick={() => {
              // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
              const redirectUrl = window.location.origin + "/dashboard";
              window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
            }}
            className="brutal-btn brutal-btn-white w-full justify-center"
          >
            <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
            Daftar dengan Google
          </button>
        </form>
      </div>
      <div className="hidden md:block bg-[#007AFF] border-l-2 border-black relative overflow-hidden order-1 md:order-2">
        <div className="absolute inset-0 noise-grid opacity-20"></div>
        <div className="p-12 relative z-10">
          <div className="pd-tag bg-[#FFD60A]">Baru di sini?</div>
          <h1 className="mt-6 font-display font-black text-6xl text-white leading-none">Gabung. Hemat. Nikmati.</h1>
          <p className="mt-6 text-white/90 text-lg max-w-md">Akun kamu adalah kunci ke dashboard patungan pribadi.</p>
        </div>
      </div>
    </div>
  );
}
