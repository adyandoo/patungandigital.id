import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, Trash, PencilSimple, DownloadSimple, X, ShieldStar, UploadSimple, FileText, Key } from "@phosphor-icons/react";
import { Modal, F, SearchInput } from "./shared";
import { useSortableTable } from "@/lib/useSortableTable";

export default function UsersTab() {
  const [users, setUsers] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showAdminModal, setShowAdminModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
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

  const { sorted, HeaderButton } = useSortableTable(filtered, null, "asc", {
    "referral_credit": (r) => r.referral_credit || 0,
  });

  const del = async (id) => {
    if (!window.confirm("Hapus user ini?")) return;
    await api.delete(`/admin/users/${id}`);
    toast.success("User dihapus");
    load();
  };
  const resetPw = async (u) => {
    if (!window.confirm(`Reset password untuk ${u.email}? User akan menerima email pemberitahuan (jika SendGrid aktif) dan bisa login pakai password default.`)) return;
    try {
      const { data } = await api.post(`/admin/users/${u.id}/reset-password`, { notify_email: true });
      const notified = data.email?.sent ? " (email terkirim)" : data.email?.mocked ? " (email mock — SendGrid belum aktif)" : "";
      toast.success(`Password direset ke: ${data.default_password}${notified}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
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
  const downloadTemplate = async () => {
    try {
      const { data } = await api.get("/admin/users/template.csv", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([data]));
      const a = document.createElement("a"); a.href = url; a.download = "users_template.csv"; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error("Gagal download template"); }
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
          <button data-testid="users-template-csv" onClick={downloadTemplate} className="brutal-btn brutal-btn-white text-sm">
            <FileText weight="bold" /> Template CSV
          </button>
          <button data-testid="users-import-csv" onClick={() => setShowImportModal(true)} className="brutal-btn brutal-btn-blue text-sm">
            <UploadSimple weight="bold" /> Import CSV
          </button>
          <button data-testid="users-export-csv" onClick={exportCSV} className="brutal-btn brutal-btn-white text-sm">
            <DownloadSimple weight="bold" /> Export CSV
          </button>
          <button data-testid="admin-add-user" className="brutal-btn brutal-btn-red text-sm" onClick={() => { setEditing(null); setShowModal(true); }}>
            <PlusCircle weight="bold" /> Tambah User
          </button>
          <button data-testid="admin-create-admin" className="brutal-btn brutal-btn-yellow text-sm" onClick={() => setShowAdminModal(true)}>
            <ShieldStar weight="bold" /> Buat Admin
          </button>
        </div>
      </div>
      <div className="brutal overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-black text-white">
            <tr>
              <th className="px-3 py-3"><input type="checkbox" checked={allSelected} onChange={toggleAll} data-testid="users-select-all" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="name" label="Nama" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="email" label="Email" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="username" label="Username" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="whatsapp" label="WhatsApp" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="referral_code" label="Kode Ref" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="referral_credit" label="Kredit" /></th>
              <th className="text-left px-4 py-3"><HeaderButton k="role" label="Role" /></th>
              <th className="text-left px-4 py-3 font-mono uppercase text-xs">Aksi</th>
            </tr>
          </thead>
          <tbody data-testid="users-table">
            {sorted.map((u) => (
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
                  <button data-testid={`user-edit-${u.id}`} onClick={() => { setEditing(u); setShowModal(true); }} className="brutal-sm px-2 py-1 bg-[#007AFF] text-white" title="Edit"><PencilSimple weight="bold" /></button>
                  <button data-testid={`user-reset-pw-${u.id}`} onClick={() => resetPw(u)} className="brutal-sm px-2 py-1 bg-[#FFD60A]" title="Reset password ke default"><Key weight="bold" /></button>
                  {u.role !== "admin" && (
                    <button data-testid={`user-delete-${u.id}`} onClick={() => del(u.id)} className="brutal-sm px-2 py-1 bg-[#FF3B30] text-white" title="Hapus"><Trash weight="bold" /></button>
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
      {showAdminModal && <AdminModal onClose={() => setShowAdminModal(false)} onSaved={() => { setShowAdminModal(false); load(); }} />}
      {showImportModal && <ImportModal onClose={() => setShowImportModal(false)} onDone={() => { setShowImportModal(false); load(); }} />}
    </div>
  );
}

function ImportModal({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return toast.error("Pilih file CSV dulu.");
    setBusy(true);
    try {
      const b64 = await new Promise((res, rej) => {
        const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(file);
      });
      const { data } = await api.post("/admin/users/import", { file_base64: b64, file_name: file.name });
      setResult(data);
      toast.success(`Selesai: ${data.summary.created} dibuat, ${data.summary.skipped} dilewati, ${data.summary.errors} error.`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <Modal onClose={onClose} title="Import User (CSV)">
      {!result ? (
        <form onSubmit={submit} className="space-y-3" data-testid="import-modal-form">
          <div className="brutal-sm bg-[#FFD60A]/40 p-3 text-sm">
            Upload CSV dengan kolom <code>name, email, username, whatsapp, gender, password</code>. Hanya <b>email</b> yang wajib. Baris dengan email duplikat akan dilewati. Password kosong akan pakai <b>default</b> yang bisa diatur di tab <b>Auto Invoice</b>.
          </div>
          <label className="brutal-btn brutal-btn-blue cursor-pointer w-full justify-center" data-testid="import-file-input-label">
            <UploadSimple weight="bold" /> {file ? file.name : "Pilih file CSV"}
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => setFile(e.target.files[0])} data-testid="import-file-input" />
          </label>
          <button type="submit" disabled={busy} className="brutal-btn brutal-btn-red w-full justify-center" data-testid="import-submit">
            {busy ? "Mengimpor..." : "Mulai Import"}
          </button>
        </form>
      ) : (
        <div className="space-y-3" data-testid="import-result">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="brutal-sm bg-[#34C759] text-white p-3">
              <div className="font-display font-black text-2xl">{result.summary.created}</div>
              <div className="text-xs font-mono uppercase">Dibuat</div>
            </div>
            <div className="brutal-sm bg-[#FFD60A] p-3">
              <div className="font-display font-black text-2xl">{result.summary.skipped}</div>
              <div className="text-xs font-mono uppercase">Dilewati</div>
            </div>
            <div className="brutal-sm bg-[#FF3B30] text-white p-3">
              <div className="font-display font-black text-2xl">{result.summary.errors}</div>
              <div className="text-xs font-mono uppercase">Error</div>
            </div>
          </div>
          {result.summary.created > 0 && (
            <div className="text-xs text-gray-700">Password default digunakan untuk yang kosong: <code>{result.default_password_used}</code></div>
          )}
          {(result.skipped.length + result.errors.length) > 0 && (
            <div className="brutal-sm bg-white p-3 max-h-48 overflow-y-auto text-xs">
              {result.skipped.map((s, i) => <div key={"s"+i}>Row {s.row}: {s.email} — <span className="text-yellow-800">{s.reason}</span></div>)}
              {result.errors.map((s, i) => <div key={"e"+i}>Row {s.row}: {s.email} — <span className="text-red-800">{s.reason}</span></div>)}
            </div>
          )}
          <button onClick={onDone} className="brutal-btn brutal-btn-red w-full justify-center" data-testid="import-done">Selesai</button>
        </div>
      )}
    </Modal>
  );
}

function AdminModal({ onClose, onSaved }) {
  const [form, setForm] = useState({ email: "", name: "", username: "", password: "" });
  const save = async (e) => {
    e.preventDefault();
    if ((form.password || "").length < 8) return toast.error("Password admin minimal 8 karakter.");
    try {
      await api.post("/admin/create-admin", form);
      toast.success("Admin baru dibuat.");
      onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Modal onClose={onClose} title="Buat Admin Baru">
      <form onSubmit={save} className="space-y-3" data-testid="admin-modal-form">
        <div className="brutal-sm bg-[#FFD60A]/40 p-3 text-sm">
          Admin baru bisa mengelola user, layanan, dan pembayaran seperti kamu. Beri password kuat minimal 8 karakter.
        </div>
        <F label="Nama"><input required className="brutal-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="am-name" /></F>
        <F label="Email"><input required type="email" className="brutal-input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="am-email" /></F>
        <F label="Username (opsional)"><input className="brutal-input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></F>
        <F label="Password (min 8)"><input required type="password" minLength={8} className="brutal-input" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="am-password" /></F>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="am-save">Buat Admin</button>
      </form>
    </Modal>
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
