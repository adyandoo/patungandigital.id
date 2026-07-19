import { useEffect, useMemo, useState } from "react";
import api, { rupiah, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, PaperPlaneTilt, Eye, Image as ImageIcon, DownloadSimple } from "@phosphor-icons/react";
import { Modal, F, SearchInput } from "./shared";

export default function PaymentsTab() {
  const [payments, setPayments] = useState([]);
  const [subs, setSubs] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [viewReceipt, setViewReceipt] = useState(null);
  const [selected, setSelected] = useState([]);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const load = async () => {
    const [p, s] = await Promise.all([api.get("/admin/payments"), api.get("/admin/subscriptions")]);
    setPayments(p.data); setSubs(s.data); setSelected([]);
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return payments.filter((p) => {
      if (statusFilter !== "all" && p.status !== statusFilter) return false;
      if (!needle) return true;
      return [p.user?.name, p.user?.email, p.service_name, p.period_label, p.status].some((v) =>
        String(v || "").toLowerCase().includes(needle)
      );
    });
  }, [payments, q, statusFilter]);

  const setStatus = async (id, status) => {
    await api.patch(`/admin/payments/${id}`, { status });
    toast.success("Status diperbarui"); load();
  };
  const remind = async (id) => {
    const { data } = await api.post(`/admin/send-reminder/${id}`);
    toast.success(`Reminder ${data.mocked ? "(MOCKED)" : ""} dikirim. Email: ${data.email_sent}, WA: ${data.whatsapp_sent}`);
  };
  const bulkRemind = async () => {
    if (selected.length === 0) return toast.error("Pilih dulu tagihannya");
    const { data } = await api.post("/admin/payments/bulk-remind", { ids: selected });
    const mocked = data.results.some((r) => r.mocked);
    toast.success(`${data.count} reminder terkirim ${mocked ? "(sebagian MOCKED)" : ""}`);
    load();
  };
  const exportCSV = () => {
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/admin/payments/export.csv?_=${Date.now()}`, "_blank");
  };
  const toggle = (id) => setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  const allSelected = filtered.length > 0 && filtered.every((p) => selected.includes(p.id));
  const toggleAll = () => setSelected(allSelected ? [] : filtered.map((p) => p.id));

  return (
    <div>
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="font-display font-bold text-2xl">Payments ({filtered.length}/{payments.length})</h2>
          <SearchInput value={q} onChange={setQ} placeholder="Cari user, layanan, periode..." testid="payments-search" />
          <select data-testid="payments-status-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="brutal-sm bg-white px-3 py-2 text-sm border-2 border-black">
            <option value="all">Semua status</option>
            <option value="pending">pending</option>
            <option value="review">review</option>
            <option value="paid">paid</option>
            <option value="overdue">overdue</option>
          </select>
        </div>
        <div className="flex gap-2 flex-wrap">
          {selected.length > 0 && (
            <button data-testid="payments-bulk-remind" onClick={bulkRemind} className="brutal-btn brutal-btn-yellow text-sm">
              <PaperPlaneTilt weight="bold" /> Kirim reminder {selected.length}
            </button>
          )}
          <button data-testid="payments-export-csv" onClick={exportCSV} className="brutal-btn brutal-btn-white text-sm">
            <DownloadSimple weight="bold" /> Export CSV
          </button>
          <button data-testid="admin-add-payment" className="brutal-btn brutal-btn-red text-sm" onClick={() => setShowModal(true)}><PlusCircle weight="bold" /> Buat Tagihan</button>
        </div>
      </div>
      <div className="brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-black text-white">
            <tr>
              <th className="px-3 py-3"><input type="checkbox" checked={allSelected} onChange={toggleAll} data-testid="payments-select-all" /></th>
              {["User", "Service", "Periode", "Jumlah", "Jatuh Tempo", "Status", "Bukti", "Aksi"].map((h) => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs">{h}</th>)}
            </tr>
          </thead>
          <tbody data-testid="payments-table">
            {filtered.map((p) => (
              <tr key={p.id} className="border-t-2 border-black">
                <td className="px-3 py-3"><input type="checkbox" data-testid={`payment-check-${p.id}`} checked={selected.includes(p.id)} onChange={() => toggle(p.id)} /></td>
                <td className="px-4 py-3 font-semibold">{p.user?.name || "?"}</td>
                <td className="px-4 py-3">{p.service_name}</td>
                <td className="px-4 py-3">{p.period_label || "-"}</td>
                <td className="px-4 py-3">
                  {rupiah(p.amount)}
                  {p.referral_credit_applied > 0 && <div className="text-xs text-[#34C759] font-mono">-{rupiah(p.referral_credit_applied)} ref</div>}
                </td>
                <td className="px-4 py-3">{p.due_date ? new Date(p.due_date).toLocaleDateString("id-ID") : "-"}</td>
                <td className="px-4 py-3">
                  <select value={p.status} onChange={(e) => setStatus(p.id, e.target.value)} className="brutal-input py-1 px-2 text-xs">
                    <option value="pending">pending</option><option value="review">review</option><option value="paid">paid</option><option value="overdue">overdue</option>
                  </select>
                </td>
                <td className="px-4 py-3">
                  {p.receipt ? (
                    <button onClick={() => setViewReceipt(p.receipt)} className="brutal-sm p-2 bg-[#007AFF] text-white text-xs"><Eye /> Lihat</button>
                  ) : <span className="text-gray-500 text-xs">-</span>}
                </td>
                <td className="px-4 py-3">
                  <button onClick={() => remind(p.id)} className="brutal-sm p-2 bg-[#FFD60A] text-xs" title="Kirim pengingat"><PaperPlaneTilt weight="bold" /></button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-600">Tidak ada hasil.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {showModal && <PaymentModal subs={subs} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
      {viewReceipt && (
        <Modal onClose={() => setViewReceipt(null)} title={`Bukti transfer: ${viewReceipt.file_name}`}>
          <div className="text-xs text-gray-600 mb-3">Diunggah: {new Date(viewReceipt.uploaded_at).toLocaleString("id-ID")}</div>
          {viewReceipt.file_base64.startsWith("data:image") ? (
            <img src={viewReceipt.file_base64} alt="Receipt" className="max-h-[70vh] mx-auto border-2 border-black" />
          ) : (
            <a href={viewReceipt.file_base64} download={viewReceipt.file_name} className="brutal-btn brutal-btn-blue"><ImageIcon /> Download file</a>
          )}
        </Modal>
      )}
    </div>
  );
}

function PaymentModal({ subs, onClose, onSaved }) {
  const [form, setForm] = useState({ subscription_id: "", amount: 0, due_date: "", period_label: "" });
  const save = async (e) => {
    e.preventDefault();
    try {
      await api.post("/admin/payments", {
        ...form,
        amount: Number(form.amount),
        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
      });
      toast.success("Tagihan dibuat"); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Modal onClose={onClose} title="Buat Tagihan">
      <form onSubmit={save} className="space-y-3" data-testid="pay-modal-form">
        <F label="Subscription">
          <select required className="brutal-input" value={form.subscription_id} onChange={(e) => { const s = subs.find((x) => x.id === e.target.value); setForm({ ...form, subscription_id: e.target.value, amount: s?.price || 0 }); }}>
            <option value="">Pilih...</option>
            {subs.map((s) => <option key={s.id} value={s.id}>{s.user?.name} — {s.service?.name} ({s.role})</option>)}
          </select>
        </F>
        <F label="Periode (contoh: Feb 2026)"><input required className="brutal-input" value={form.period_label} onChange={(e) => setForm({ ...form, period_label: e.target.value })} /></F>
        <F label="Jumlah (Rp)"><input type="number" required className="brutal-input" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></F>
        <F label="Jatuh tempo"><input type="date" className="brutal-input" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></F>
        <div className="text-xs text-gray-600">Note: kredit referral user (jika ada) akan otomatis dipotong dari jumlah. Snap invoice Midtrans juga dibuat otomatis.</div>
        <button type="submit" className="brutal-btn brutal-btn-red">Buat tagihan</button>
      </form>
    </Modal>
  );
}
