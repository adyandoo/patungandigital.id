import { useEffect, useMemo, useState } from "react";
import api, { rupiah, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, Trash } from "@phosphor-icons/react";
import { Modal, F, SearchInput } from "./shared";
import DatePicker from "@/components/DatePicker";

export default function SubscriptionsTab() {
  const [subs, setSubs] = useState([]);
  const [users, setUsers] = useState([]);
  const [services, setServices] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [q, setQ] = useState("");

  const load = async () => {
    const [s, u, sv] = await Promise.all([api.get("/admin/subscriptions"), api.get("/admin/users"), api.get("/admin/services")]);
    setSubs(s.data); setUsers(u.data); setServices(sv.data);
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return subs;
    return subs.filter((s) =>
      [s.user?.name, s.user?.email, s.service?.name, s.role, s.status].some((v) => String(v || "").toLowerCase().includes(needle))
    );
  }, [subs, q]);

  const del = async (id) => {
    if (!window.confirm("Hapus subscription?")) return;
    await api.delete(`/admin/subscriptions/${id}`);
    toast.success("Dihapus"); load();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="font-display font-bold text-2xl">Subscriptions ({filtered.length}/{subs.length})</h2>
          <SearchInput value={q} onChange={setQ} placeholder="Cari user, layanan..." testid="subs-search" />
        </div>
        <button data-testid="admin-add-sub" className="brutal-btn brutal-btn-red" onClick={() => setShowModal(true)}><PlusCircle weight="bold" /> Tempatkan User</button>
      </div>
      <div className="brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-black text-white">
            <tr>{["User", "Service", "Role", "Group", "Mulai", "Harga", "Status", "Aksi"].map((h) => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs">{h}</th>)}</tr>
          </thead>
          <tbody data-testid="subs-table">
            {filtered.map((s) => (
              <tr key={s.id} className="border-t-2 border-black">
                <td className="px-4 py-3 font-semibold">{s.user?.name || "?"}</td>
                <td className="px-4 py-3">{s.service?.name}</td>
                <td className="px-4 py-3"><span className="pd-tag">{s.role}</span></td>
                <td className="px-4 py-3 font-mono text-xs">{s.group_id ? s.group_id.slice(-6) : "-"}</td>
                <td className="px-4 py-3">{s.start_date ? new Date(s.start_date).toLocaleDateString("id-ID") : "-"}</td>
                <td className="px-4 py-3">{rupiah(s.price)}</td>
                <td className="px-4 py-3"><span className="pd-tag">{s.status}</span></td>
                <td className="px-4 py-3">
                  <button onClick={() => del(s.id)} className="brutal-sm p-2 bg-[#FF3B30] text-white"><Trash /></button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-600">Tidak ada hasil.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {showModal && <SubModal users={users} services={services} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function SubModal({ users, services, onClose, onSaved }) {
  const [form, setForm] = useState({
    user_id: "", service_id: "", role: "regular", group_id: "",
    start_date: new Date().toISOString().slice(0, 10),
    end_date: "", price: 0, status: "active", duration_months: 1,
  });
  const [suggested, setSuggested] = useState([]);

  useEffect(() => {
    if (!form.service_id) { setSuggested([]); return; }
    api.get(`/admin/groups/suggest?service_id=${form.service_id}&role=${form.role}`)
      .then((r) => setSuggested(r.data))
      .catch(() => setSuggested([]));
  }, [form.service_id, form.role]);

  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...form, price: Number(form.price),
        duration_months: Number(form.duration_months) || 1,
        group_id: form.group_id || null,
        start_date: new Date(form.start_date).toISOString(),
        end_date: form.end_date ? new Date(form.end_date).toISOString() : null,
      };
      await api.post("/admin/subscriptions", payload);
      toast.success("Subscription dibuat"); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Modal onClose={onClose} title="Tempatkan User ke Service">
      <form onSubmit={save} className="space-y-3" data-testid="sub-modal-form">
        <F label="User">
          <select required className="brutal-input" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} data-testid="submod-user">
            <option value="">Pilih user...</option>
            {users.filter((u) => u.role === "user").map((u) => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}
          </select>
        </F>
        <F label="Service">
          <select required className="brutal-input" value={form.service_id} onChange={(e) => { const svc = services.find((s) => s.id === e.target.value); setForm({ ...form, service_id: e.target.value, price: svc?.price_regular || 0, group_id: "" }); }} data-testid="submod-service">
            <option value="">Pilih service...</option>
            {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Role">
            <select className="brutal-input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="submod-role">
              <option value="regular">Regular</option><option value="host">Host</option>
            </select>
          </F>
          <F label="Harga (Rp)"><input type="number" className="brutal-input" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></F>
          <F label="Durasi default (bulan)"><input type="number" min={1} max={24} className="brutal-input" value={form.duration_months} onChange={(e) => setForm({ ...form, duration_months: e.target.value })} data-testid="sub-modal-duration" /></F>
        </div>
        <F label="Assign ke group (opsional)">
          <select className="brutal-input" value={form.group_id} onChange={(e) => setForm({ ...form, group_id: e.target.value })} data-testid="submod-group">
            <option value="">— Tidak sekarang (assign nanti dari tab Groups) —</option>
            {suggested.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} — {g.filled_regular}/{g.regular_slots} reg, {g.filled_host}/{g.host_slots} host — {g.available_for_role} slot {form.role} tersedia
              </option>
            ))}
          </select>
          {form.service_id && suggested.length === 0 && (
            <div className="text-xs text-[#FF3B30] mt-1 font-mono">Semua group untuk service ini penuh untuk role {form.role}. Buat group baru dulu di tab Groups.</div>
          )}
        </F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Mulai"><DatePicker value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} testId="sub-modal-start" placeholder="Pilih tanggal mulai" allowClear={false} /></F>
          <F label="Sampai (opsional)"><DatePicker value={form.end_date} onChange={(v) => setForm({ ...form, end_date: v })} testId="sub-modal-end" placeholder="Pilih tanggal berakhir" /></F>
        </div>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="submod-save">Simpan</button>
      </form>
    </Modal>
  );
}
