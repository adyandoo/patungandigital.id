import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { CalendarPlus, Lightning, Key } from "@phosphor-icons/react";
import { F, Note } from "./shared";

export default function AutoInvoiceTab() {
  const [icfg, setIcfg] = useState(null);
  const [gcfg, setGcfg] = useState(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.get("/admin/invoice-config").then((r) => setIcfg(r.data));
    api.get("/admin/general-config").then((r) => setGcfg(r.data));
  }, []);

  if (!icfg || !gcfg) return <div className="brutal p-8">Memuat...</div>;

  const saveInvoice = async (e) => {
    e.preventDefault();
    try {
      await api.put("/admin/invoice-config", {
        day_of_month: Number(icfg.day_of_month),
        due_days: Number(icfg.due_days),
        enabled: !!icfg.enabled,
      });
      toast.success("Konfigurasi auto-invoice tersimpan.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const saveGeneral = async (e) => {
    e.preventDefault();
    if ((gcfg.default_new_user_password || "").length < 6)
      return toast.error("Password default minimal 6 karakter.");
    try {
      await api.put("/admin/general-config", { default_new_user_password: gcfg.default_new_user_password });
      toast.success("Password default tersimpan.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const runNow = async () => {
    if (!window.confirm("Buat invoice bulan ini untuk semua subscription aktif sekarang? (Idempoten — tidak akan duplikat)")) return;
    setRunning(true);
    try {
      const { data } = await api.post("/admin/invoices/generate-now");
      toast.success(`Selesai: ${data.count} invoice dibuat, ${data.skipped} dilewati (sudah ada). Periode: ${data.period}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setRunning(false); }
  };

  return (
    <div className="grid md:grid-cols-3 gap-6" data-testid="auto-invoice-tab">
      <form onSubmit={saveInvoice} className="brutal p-6 md:col-span-2 space-y-4" data-testid="invoice-config-form">
        <div className="flex items-center gap-2">
          <CalendarPlus weight="duotone" size={28} />
          <h2 className="font-display font-bold text-2xl">Auto-Invoice Generator</h2>
        </div>
        <Note title="Bagaimana cara kerjanya?" body="Setiap jam scheduler cek: kalau tanggal hari ini = tanggal generate, buat invoice PENDING untuk semua subscription berstatus 'active'. Idempoten — kalau invoice periode bulan itu sudah ada untuk sub yang sama, di-skip." />
        <div className="grid grid-cols-2 gap-4">
          <F label="Tanggal generate tiap bulan (1–28)">
            <input type="number" min={1} max={28} className="brutal-input" value={icfg.day_of_month} onChange={(e) => setIcfg({ ...icfg, day_of_month: e.target.value })} data-testid="invoice-day-input" />
          </F>
          <F label="Jatuh tempo (hari setelah generate)">
            <input type="number" min={1} max={60} className="brutal-input" value={icfg.due_days} onChange={(e) => setIcfg({ ...icfg, due_days: e.target.value })} data-testid="invoice-due-input" />
          </F>
        </div>
        <label className="flex items-center gap-2 font-mono text-sm">
          <input type="checkbox" checked={!!icfg.enabled} onChange={(e) => setIcfg({ ...icfg, enabled: e.target.checked })} data-testid="invoice-enabled" />
          Aktifkan generator otomatis
        </label>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="invoice-config-save">Simpan konfigurasi</button>
      </form>

      <div className="brutal p-6 bg-[#FFD60A]/30 h-fit">
        <div className="font-display font-bold text-xl flex items-center gap-2"><Lightning weight="fill" /> Jalankan sekarang</div>
        <p className="text-sm mt-2">Force-generate invoice bulan ini tanpa menunggu tanggal terjadwal. Tetap idempoten.</p>
        <button onClick={runNow} disabled={running} className="brutal-btn brutal-btn-blue mt-4 w-full justify-center" data-testid="invoice-run-now">
          {running ? "Menjalankan..." : "Generate invoice sekarang"}
        </button>
      </div>

      <form onSubmit={saveGeneral} className="brutal p-6 md:col-span-3 space-y-3" data-testid="general-config-form">
        <div className="flex items-center gap-2">
          <Key weight="duotone" size={24} />
          <h3 className="font-display font-bold text-xl">Password default untuk import user</h3>
        </div>
        <p className="text-sm text-gray-700">Digunakan saat kolom <code>password</code> di CSV kosong. User bisa ganti password setelah login pertama.</p>
        <div className="max-w-sm">
          <F label="Default password baru">
            <input className="brutal-input" value={gcfg.default_new_user_password} onChange={(e) => setGcfg({ ...gcfg, default_new_user_password: e.target.value })} data-testid="general-default-pw" />
          </F>
        </div>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="general-config-save">Simpan password default</button>
      </form>
    </div>
  );
}
