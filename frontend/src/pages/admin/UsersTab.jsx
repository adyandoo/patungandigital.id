import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, Trash, PencilSimple, DownloadSimple, X } from "@phosphor-icons/react";
import { Modal, F, SearchInput } from "./shared";

export default function UsersTab() {
  const [users, setUsers] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState([]);
  const [q, setQ] = useState("");

  const load = () => api.get("/admin/users").then((r) => { setUsers(r.data); setSelected([]); });
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return users;
    return users.filter((u) =>
      [u.name, u.email, u.username, u.whatsapp, u.role, u.referral_code].some((v) => String(v || "").toLowerCase().includes(needle))
    );
  }, [users, q]);

  const del = async (id) => {
    if (!window.confirm("Hapus user ini?")) return;
    await api.delete(`/admin/users/${id}`);
    toast.success("User dihapus");
    load();
  };
  const bulkDelete = async () => {
    if (selected.length === 0) return toast.error("Pilih dulu user-nya");
    if (!window.confirm(`Hapus ${selected.length} user? (Admin akan dilewati)`)) return;
    const { data } = await api.post("/admin/users/bulk-delete", { ids: selected });
    toast.success(`${data.deleted} user dihapus${data.skipped_admins ? ` (${data.skipped_admins} admin dilewati)` : ""}`);
    load();
  };
  const exportCSV = () => {
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/admin/users/export.csv?_=${Date.now()}`, "_blank");
  };
  const toggle = (id) => setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  const selectableIds = filtered.filter((u) => u.role !== "admin").map((u) => u.id);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => selected.includes(id));
  const toggleAll = () => setSelected(allSelected ? [] : selectableIds);

  return (
    <div>
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="font-display font-bold text-2xl">Users ({filtered.length}/{users.length})</h2>
          <SearchInput value={q} onChange={setQ} placeholder="Cari nama, email, WA, kode..." testid="users-search" />
        </div>
        <div className="flex gap-2 flex-wrap">
          {selected.length > 0 && (
            <button data-testid="users-bulk-delete" onClick={bulkDelete} className="brutal-btn brutal-btn-red text-sm">
              <Trash weight="bold" /> Hapus {selected.length}
            </button>
          )}
          <button data-testid="users-export-csv" onClick={exportCSV} className="brutal-btn brutal-btn-white text-sm">
            <DownloadSimple weight="bold" /> Export CSV
          </button>
          <button data-testid="admin-add-user" className="brutal-btn brutal-btn-red text-sm" onClick={() => { setEditing(null); setShowModal(true); }}>
            <PlusCircle weight="bold" /> Tambah User
          </button>
        </div>
      </div>
      <div className="brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-black text-white">
            <tr>
              <th className="px-3 py-3"><input type="checkbox" checked={allSelected} onChange={toggleAll} data-testid="users-select-all" /></th>
              {["Nama", "Email", "Username", "WhatsApp", "Kode Ref", "Kredit", "Role", "Aksi"].map((h) => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs">{h}</th>)}
            </tr>
          </thead>
          <tbody data-testid="users-table">
            {filtered.map((u) => (
              <tr key={u.id} className="border-t-2 border-black" data-testid={`user-row-${u.id}`}>
                <td className="px-3 py-3">
                  {u.role !== "admin" && (
                    <input type="checkbox" data-testid={`user-check-${u.id}`} checked={selected.includes(u.id)} onChange={() => toggle(u.id)} />
                  )}
                </td>
                <td className="px-4 py-3 font-semibold">{u.name}</td>
                <td className="px-4 py-3">{u.email}</td>
                <td className="px-4 py-3">{u.username || "-"}</td>
                <td className="px-4 py-3">{u.whatsapp || "-"}</td>
                <td className="px-4 py-3 font-mono text-xs">{u.referral_code || "-"}</td>
                <td className="px-4 py-3 font-mono text-xs">{u.referral_credit ? `Rp ${u.referral_credit.toLocaleString("id-ID")}` : "-"}</td>
                <td className="px-4 py-3"><span className="pd-tag">{u.role}</span></td>
                <td className="px-4 py-3 flex gap-2">
                  <button data-testid={`user-edit-${u.id}`} onClick={() => { setEditing(u); setShowModal(true); }} className="brutal-sm px-2 py-1 bg-[#007AFF] text-white"><PencilSimple weight="bold" /></button>
                  {u.role !== "admin" && (
                    <button data-testid={`user-delete-${u.id}`} onClick={() => del(u.id)} className="brutal-sm px-2 py-1 bg-[#FF3B30] text-white"><Trash weight="bold" /></button>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-600">Tidak ada hasil.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {showModal && <UserModal user={editing} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function UserModal({ user, onClose, onSaved }) {
  const [form, setForm] = useState({
    email: user?.email || "",
    name: user?.name || "",
    username: user?.username || "",
    whatsapp: user?.whatsapp || "",
    gender: user?.gender || "",
    role: user?.role || "user",
    password: "",
    extra_key: "",
    extra_value: "",
  });
  const [extra, setExtra] = useState(user?.extra || {});

  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form, extra };
      if (!payload.password) delete payload.password;
      delete payload.extra_key; delete payload.extra_value;
      if (user) await api.patch(`/admin/users/${user.id}`, payload);
      else await api.post("/admin/users", payload);
      toast.success("User tersimpan");
      onSaved();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const addExtra = () => {
    if (!form.extra_key) return;
    setExtra({ ...extra, [form.extra_key]: form.extra_value });
    setForm({ ...form, extra_key: "", extra_value: "" });
  };

  return (
    <Modal onClose={onClose} title={user ? "Edit User" : "Tambah User"}>
      <form onSubmit={save} className="space-y-4" data-testid="user-modal-form">
        <div className="grid grid-cols-2 gap-3">
          <F label="Email"><input required type="email" className="brutal-input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="um-email" /></F>
          <F label="Nama"><input required className="brutal-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="um-name" /></F>
          <F label="Username"><input className="brutal-input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></F>
          <F label="WhatsApp"><input className="brutal-input" value={form.whatsapp} onChange={(e) => setForm({ ...form, whatsapp: e.target.value })} /></F>
          <F label="Gender">
            <select className="brutal-input" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
              <option value="">-</option><option value="L">Laki-laki</option><option value="P">Perempuan</option>
            </select>
          </F>
          <F label="Role">
            <select className="brutal-input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="user">User</option><option value="admin">Admin</option>
            </select>
          </F>
          <F label={user ? "Password baru (opsional)" : "Password"}><input type="password" className="brutal-input" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></F>
        </div>
        <div>
          <div className="font-mono text-xs uppercase mb-2">Info tambahan (custom)</div>
          <div className="flex gap-2">
            <input placeholder="key" className="brutal-input" value={form.extra_key} onChange={(e) => setForm({ ...form, extra_key: e.target.value })} />
            <input placeholder="value" className="brutal-input" value={form.extra_value} onChange={(e) => setForm({ ...form, extra_value: e.target.value })} />
            <button type="button" className="brutal-btn brutal-btn-blue" onClick={addExtra}>Tambah</button>
          </div>
          <div className="mt-2 space-y-1">
            {Object.entries(extra).map(([k, v]) => (
              <div key={k} className="brutal-sm p-2 flex justify-between items-center bg-white">
                <span className="text-sm"><b>{k}:</b> {String(v)}</span>
                <button type="button" onClick={() => { const n = { ...extra }; delete n[k]; setExtra(n); }}><X weight="bold" /></button>
              </div>
            ))}
          </div>
        </div>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="um-save">Simpan</button>
      </form>
    </Modal>
  );
}
