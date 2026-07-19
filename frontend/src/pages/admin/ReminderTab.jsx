import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Lightning } from "@phosphor-icons/react";
import { F } from "./shared";

export default function ReminderTab() {
  const [cfg, setCfg] = useState(null);
  const [running, setRunning] = useState(false);
  useEffect(() => { api.get("/admin/reminder-config").then((r) => setCfg(r.data)); }, []);
  if (!cfg) return <div>Memuat...</div>;
  const save = async (e) => {
    e.preventDefault();
    try {
      await api.put("/admin/reminder-config", {
        days_before_due: Number(cfg.days_before_due),
        enable_email: !!cfg.enable_email,
        reminder_message: cfg.reminder_message,
      });
      toast.success("Konfigurasi tersimpan");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const runNow = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/admin/scheduler/run-now");
      toast.success(`Scheduler dijalankan: ${data.count} reminder terkirim`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setRunning(false); }
  };
  return (
    <div className="grid md:grid-cols-3 gap-6">
      <form onSubmit={save} className="brutal p-8 md:col-span-2" data-testid="reminder-form">
        <h2 className="font-display font-bold text-2xl">Payment Reminder</h2>
        <p className="text-sm text-gray-700 mt-1">Scheduler otomatis jalan setiap 1 jam & kirim reminder untuk tagihan H-N sebelum jatuh tempo (belum diingatkan dalam 24 jam terakhir).</p>
        <div className="mt-6 space-y-4">
          <F label="Kirim reminder H- (hari)"><input type="number" className="brutal-input" value={cfg.days_before_due} onChange={(e) => setCfg({ ...cfg, days_before_due: e.target.value })} /></F>
          <label className="flex items-center gap-2"><input type="checkbox" checked={cfg.enable_email} onChange={(e) => setCfg({ ...cfg, enable_email: e.target.checked })} /> Aktifkan Email (SendGrid)</label>
          <F label="Template pesan (gunakan {name}, {service}, {period}, {due_date}, {amount})">
            <textarea rows="5" className="brutal-input" value={cfg.reminder_message} onChange={(e) => setCfg({ ...cfg, reminder_message: e.target.value })} />
          </F>
        </div>
        <button type="submit" className="brutal-btn brutal-btn-red mt-6" data-testid="reminder-save">Simpan konfigurasi</button>
      </form>
      <div className="brutal p-6 bg-[#FFD60A]/30 h-fit">
        <div className="font-display font-bold text-xl flex items-center gap-2"><Lightning weight="fill" /> Jalankan sekarang</div>
        <p className="text-sm mt-2">Trigger scheduler manual — akan scan semua tagihan yang jatuh tempo dalam <b>{cfg.days_before_due}</b> hari.</p>
        <button onClick={runNow} disabled={running} className="brutal-btn brutal-btn-blue mt-4 w-full justify-center" data-testid="scheduler-run-now">
          {running ? "Menjalankan..." : "Run scheduler now"}
        </button>
      </div>
    </div>
  );
}
