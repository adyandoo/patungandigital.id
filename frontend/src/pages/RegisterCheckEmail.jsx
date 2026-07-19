import { useSearchParams, Link } from "react-router-dom";
import { useState } from "react";
import { EnvelopeSimple, ArrowClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

export default function RegisterCheckEmail() {
  const [params] = useSearchParams();
  const email = params.get("email") || "";
  const [busy, setBusy] = useState(false);

  const resend = async () => {
    if (!email) return toast.error("Email tidak ditemukan di URL");
    setBusy(true);
    try {
      await api.post("/auth/resend-verification", { email });
      toast.success("Link verifikasi baru sudah dikirim (jika email terdaftar).");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-[calc(100vh-73px)] grid md:grid-cols-2">
      <div className="hidden md:block bg-[#34C759] border-r-2 border-black relative overflow-hidden">
        <div className="absolute inset-0 noise-grid opacity-30" />
        <div className="p-12 relative z-10">
          <span className="pd-tag bg-black text-white">Verifikasi</span>
          <h1 className="mt-6 font-display font-black text-6xl text-white leading-none">Cek<br />inboxmu.</h1>
          <p className="mt-6 text-white/90 max-w-md">Kami baru saja mengirim link verifikasi. Klik link tersebut untuk mengaktifkan akunmu.</p>
        </div>
      </div>
      <div className="p-8 md:p-16 flex items-center">
        <div className="w-full max-w-md" data-testid="check-email-page">
          <EnvelopeSimple weight="duotone" size={64} className="text-[#FF3B30]" />
          <h2 className="mt-4 font-display font-black text-4xl">Verifikasi email</h2>
          <p className="mt-3 text-gray-700">Kami sudah kirim link verifikasi ke:</p>
          <div className="mt-2 brutal-sm bg-[#FFD60A]/40 p-3 font-mono text-sm break-all">{email || "—"}</div>
          <div className="mt-6 space-y-3 text-sm text-gray-700">
            <div className="flex gap-3"><span className="font-display font-black">1.</span> Buka email dari <b>patungandigital.id</b> di inbox (atau folder Spam).</div>
            <div className="flex gap-3"><span className="font-display font-black">2.</span> Klik tombol <b>Verifikasi Email</b>. Link berlaku 24 jam.</div>
            <div className="flex gap-3"><span className="font-display font-black">3.</span> Kamu akan otomatis diarahkan ke dashboard.</div>
          </div>
          <button onClick={resend} disabled={busy} className="brutal-btn brutal-btn-yellow mt-8" data-testid="resend-btn">
            <ArrowClockwise weight="bold" /> {busy ? "Mengirim..." : "Kirim ulang link"}
          </button>
          <div className="mt-6 text-sm">
            Sudah verifikasi? <Link to="/login" className="underline font-semibold">Masuk sekarang</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
