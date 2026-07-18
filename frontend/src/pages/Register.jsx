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
