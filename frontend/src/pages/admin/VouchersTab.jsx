import { useEffect, useMemo, useState } from "react";
import api, { rupiah, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, Trash, Tag, Copy, PencilSimple } from "@phosphor-icons/react";
import { Modal, F, SearchInput } from "./shared";
import { useSortableTable } from "@/lib/useSortableTable";

export default function VouchersTab() {
  const [items, setItems] = useState([]);
  const [users, setUsers] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [q, setQ] = useState("");

  const load = async () => {
    const [v, u] = await Promise.all([
      api.get("/admin/vouchers"),
      api.get("/admin/users"),
    ]);
    setItems(v.data);
    setUsers(u.data);
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((v) =>
      [v.code, v.description, v.source, v.target_user?.name, v.target_user?.email].some((x) => String(x || "").toLowerCase().includes(needle))
    );
  }, [items, q]);

  const { sorted, HeaderButton } = useSortableTable(filtered, "created_at", "desc", {
    "created_at": (r) => new Date(r.created_at || 0).getTime(),
    "discount": (r) => r.discount_amount || 0,
    "target": (r) => r.target_user?.name || r.applies_to_user_id || "",
    "valid_until": (r) => new Date(r.valid_until || 0).getTime(),
  });

  const del = async (v) => {
    if (!window.confirm(`Hapus voucher ${v.code}?`)) return;
    try { await api.delete(`/admin/vouchers/${v.id}`); toast.success("Voucher dihapus."); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const copy = (code) => { navigator.clipboard.writeText(code); toast.success(`Kode ${code} disalin.`); };
  const toggleStatus = async (v) => {
    const newStatus = v.status === "active" ? "disabled" : "active";
    try {
      await api.patch(`/admin/vouchers/${v.id}`, { status: newStatus });
      toast.success(`Voucher ${newStatus === "active" ? "diaktifkan" : "dinonaktifkan"}.`);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div data-testid="admin-vouchers-tab">
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="font-display font-bold text-2xl flex items-center gap-2"><Tag weight="duotone" /> Voucher ({filtered.length}/{items.length})</h2>
          <SearchInput value={q} onChange={setQ} placeholder="Cari kode, user, source..." testid="vouchers-search" />
        </div>
        <button onClick={() => { setEditing(null); setShowModal(true); }} className="brutal-btn brutal-btn-red" data-testid="admin-add-voucher">
          <PlusCircle weight="bold" /> Tambah Voucher
        </button>
      </div>

      <div className="brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-black text-white">
            <tr>
              <th className="text-left px-4 py-3 font-mono uppercase text-xs">Kode</th>
              <th className="text-left px-4 py-3"><HeaderButton k="discount" label="Diskon" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="target" label="Target" /></th>
              <th className="text-left px-4 py-3 font-mono uppercase text-xs">Pemakaian</th>
              <th className="text-left px-4 py-3"><HeaderButton k="source" label="Source" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="valid_until" label="Berlaku" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="status" label="Status" /></th>
              <th className="text-left px-4 py-3 font-mono uppercase text-xs">Aksi</th>
            </tr>
          </thead>
          <tbody data-testid="vouchers-table">
            {sorted.map((v) => (
              <tr key={v.id} className="border-t-2 border-black" data-testid={`voucher-row-${v.id}`}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold">{v.code}</span>
                    <button onClick={() => copy(v.code)} className="brutal-sm p-1 bg-white" title="Salin kode"><Copy size={12} weight="bold" /></button>
                  </div>
                </td>
                <td className="px-4 py-3 font-display font-black">
                  {v.discount_percent > 0 ? `${v.discount_percent}%` : rupiah(v.discount_amount)}
                </td>
                <td className="px-4 py-3 text-xs">
                  {v.target_user ? (
                    <div>
                      <div className="font-semibold">{v.target_user.name}</div>
                      <div className="text-gray-600">{v.target_user.email}</div>
                    </div>
                  ) : (
                    <span className="pd-tag bg-[#007AFF] text-white">GLOBAL</span>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs">{v.used_count}/{v.max_uses}</td>
                <td className="px-4 py-3 text-xs"><span className="pd-tag">{v.source}</span></td>
                <td className="px-4 py-3 text-xs">{v.valid_until ? new Date(v.valid_until).toLocaleDateString("id-ID") : "-"}</td>
                <td className="px-4 py-3">
                  <button onClick={() => toggleStatus(v)} className={`brutal-sm px-2 py-1 text-xs font-mono uppercase ${v.status === "active" ? "bg-[#34C759] text-white" : "bg-gray-300"}`} data-testid={`voucher-status-${v.id}`}>
                    {v.status}
                  </button>
                </td>
                <td className="px-4 py-3 flex gap-1">
                  <button onClick={() => { setEditing(v); setShowModal(true); }} className="brutal-sm p-2 bg-[#007AFF] text-white" data-testid={`voucher-edit-${v.id}`}><PencilSimple size={12} weight="bold" /></button>
                  <button onClick={() => del(v)} className="brutal-sm p-2 bg-[#FF3B30] text-white" data-testid={`voucher-delete-${v.id}`}><Trash size={12} weight="bold" /></button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-600">Belum ada voucher. Klik "Tambah Voucher" untuk membuatnya.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showModal && <VoucherModal voucher={editing} users={users} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function VoucherModal({ voucher, users, onClose, onSaved }) {
  const isEdit = !!voucher;
  const [form, setForm] = useState({
    code: voucher?.code || "",
    description: voucher?.description || "",
    discount_amount: voucher?.discount_amount || 0,
    discount_percent: voucher?.discount_percent || 0,
    max_uses: voucher?.max_uses || 1,
    valid_days: 30,
    applies_to_user_id: voucher?.applies_to_user_id || "",
  });

  const save = async (e) => {
    e.preventDefault();
    if ((Number(form.discount_amount) || 0) <= 0 && (Number(form.discount_percent) || 0) <= 0) {
      return toast.error("Harus isi discount_amount atau discount_percent.");
    }
    try {
      if (isEdit) {
        const payload = {
          description: form.description,
          discount_amount: Number(form.discount_amount),
          discount_percent: Number(form.discount_percent),
          max_uses: Number(form.max_uses),
          applies_to_user_id: form.applies_to_user_id || null,
        };
        await api.patch(`/admin/vouchers/${voucher.id}`, payload);
        toast.success("Voucher diupdate.");
      } else {
        const payload = {
          code: form.code || undefined,
          description: form.description,
          discount_amount: Number(form.discount_amount),
          discount_percent: Number(form.discount_percent),
          max_uses: Number(form.max_uses),
          valid_days: Number(form.valid_days),
          applies_to_user_id: form.applies_to_user_id || null,
          source: "admin_manual",
        };
        await api.post("/admin/vouchers", payload);
        toast.success("Voucher dibuat.");
      }
      onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Modal onClose={onClose} title={isEdit ? "Edit Voucher" : "Buat Voucher Baru"}>
      <form onSubmit={save} className="space-y-3" data-testid="voucher-modal-form">
        <F label="Kode (opsional — auto-generate jika kosong)">
          <input className="brutal-input font-mono uppercase" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} disabled={isEdit} placeholder="KODE-VOUCHER" data-testid="voucher-code-input" />
        </F>
        <F label="Deskripsi">
          <input className="brutal-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Contoh: Voucher promo Ramadhan" data-testid="voucher-desc-input" />
        </F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Diskon (Rp)">
            <input type="number" min={0} className="brutal-input" value={form.discount_amount} onChange={(e) => setForm({ ...form, discount_amount: e.target.value })} data-testid="voucher-amount-input" />
          </F>
          <F label="Diskon (%)">
            <input type="number" min={0} max={100} step="0.1" className="brutal-input" value={form.discount_percent} onChange={(e) => setForm({ ...form, discount_percent: e.target.value })} data-testid="voucher-percent-input" />
          </F>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <F label="Max pemakaian">
            <input type="number" min={1} max={10000} className="brutal-input" value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} data-testid="voucher-max-uses" />
          </F>
          {!isEdit && (
            <F label="Berlaku (hari)">
              <input type="number" min={1} max={365} className="brutal-input" value={form.valid_days} onChange={(e) => setForm({ ...form, valid_days: e.target.value })} data-testid="voucher-valid-days" />
            </F>
          )}
        </div>
        <F label="Target user (kosong = global)">
          <select className="brutal-input" value={form.applies_to_user_id} onChange={(e) => setForm({ ...form, applies_to_user_id: e.target.value })} data-testid="voucher-target-user">
            <option value="">— Global (semua user bisa klaim) —</option>
            {users.filter((u) => u.role === "user").map((u) => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}
          </select>
        </F>
        <button type="submit" className="brutal-btn brutal-btn-red w-full justify-center" data-testid="voucher-save">
          {isEdit ? "Simpan Perubahan" : "Buat Voucher"}
        </button>
      </form>
    </Modal>
  );
}
