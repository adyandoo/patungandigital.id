import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { QrCode, CheckCircle, UploadSimple, Trash } from "@phosphor-icons/react";
import { F, Note } from "./shared";

export default function PaymentSettingsTab() {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/admin/payment-config").then((r) => setCfg(r.data));
  useEffect(() => { load(); }, []);

  if (!cfg) return <div className="brutal p-8">Memuat...</div>;

  const uploadQris = async (file) => {
    try {
      const b64 = await toBase64(file);
      setCfg({ ...cfg, qris_image_base64: b64 });
      toast.success("QRIS siap disimpan.");
    } catch { toast.error("Gagal baca file."); }
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/payment-config", {
        qris_image_base64: cfg.qris_image_base64,
        qris_notes: cfg.qris_notes || "",
        manual_bank_info: cfg.manual_bank_info || "",
        midtrans_fee_percent: Number(cfg.midtrans_fee_percent) || 5,
      });
      toast.success("Pengaturan pembayaran tersimpan.");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <div className="max-w-4xl space-y-6" data-testid="payment-settings-tab">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="font-display font-bold text-2xl flex items-center gap-2"><QrCode weight="duotone" /> Pengaturan Pembayaran</h2>
      </div>

      <Note title="Dua metode pembayaran" body="User bisa memilih Manual QRIS (tanpa biaya, direkomendasikan) atau Midtrans (otomatis, +5% biaya transaksi). Upload QRIS statis di sini — akan tampil ke user saat memilih Manual QRIS." />

      <div className="brutal p-6">
        <h3 className="font-display font-bold text-xl">1. Gambar QRIS Statis</h3>
        <p className="text-sm text-gray-700 mt-1">Ini yang akan discan user. Ganti kapan saja.</p>

        <div className="mt-4 grid md:grid-cols-2 gap-6">
          <div className="brutal-sm bg-white p-4 min-h-64 flex items-center justify-center">
            {cfg.qris_image_base64 ? (
              <img src={cfg.qris_image_base64} alt="QRIS" className="max-h-72 mx-auto" data-testid="qris-preview" />
            ) : (
              <div className="text-center text-gray-500">
                <QrCode weight="duotone" size={64} className="mx-auto" />
                <div className="mt-2 text-sm">Belum ada QRIS</div>
              </div>
            )}
          </div>
          <div className="space-y-3">
            <label className="brutal-btn brutal-btn-blue cursor-pointer" data-testid="qris-upload-btn">
              <UploadSimple weight="bold" /> Upload gambar QRIS
              <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files[0] && uploadQris(e.target.files[0])} />
            </label>
            {cfg.qris_image_base64 && (
              <button onClick={() => setCfg({ ...cfg, qris_image_base64: null })} className="brutal-btn brutal-btn-white" data-testid="qris-remove-btn">
                <Trash weight="bold" /> Hapus gambar
              </button>
            )}
            <F label="Catatan / Instruksi (opsional)">
              <textarea rows="4" className="brutal-input" value={cfg.qris_notes || ""} onChange={(e) => setCfg({ ...cfg, qris_notes: e.target.value })} placeholder="Contoh: Scan QRIS, lalu upload bukti transfer di bawah." data-testid="qris-notes" />
            </F>
            <F label="Info transfer manual (opsional)">
              <textarea rows="3" className="brutal-input" value={cfg.manual_bank_info || ""} onChange={(e) => setCfg({ ...cfg, manual_bank_info: e.target.value })} placeholder="Contoh: BCA 1234567890 a.n. patungandigital.id" data-testid="bank-info" />
            </F>
          </div>
        </div>
      </div>

      <div className="brutal p-6">
        <h3 className="font-display font-bold text-xl">2. Biaya Midtrans (%)</h3>
        <p className="text-sm text-gray-700 mt-1">Ditambahkan ke tagihan user saat mereka memilih Midtrans. Default 5%.</p>
        <div className="mt-4 flex items-center gap-3 max-w-xs">
          <input type="number" step="0.1" min="0" max="20" className="brutal-input" value={cfg.midtrans_fee_percent ?? 5} onChange={(e) => setCfg({ ...cfg, midtrans_fee_percent: e.target.value })} data-testid="midtrans-fee-input" />
          <span className="font-display font-bold text-2xl">%</span>
        </div>
      </div>

      <button onClick={save} disabled={saving} className="brutal-btn brutal-btn-red" data-testid="payment-settings-save">
        <CheckCircle weight="bold" /> {saving ? "Menyimpan..." : "Simpan pengaturan"}
      </button>
    </div>
  );
}

function toBase64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}
