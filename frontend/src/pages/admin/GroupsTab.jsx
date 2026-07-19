import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, Trash, PencilSimple, Key, UsersThree, Copy } from "@phosphor-icons/react";
import { Modal, F, SearchInput } from "./shared";

export default function GroupsTab() {
  const [groups, setGroups] = useState([]);
  const [services, setServices] = useState([]);
  const [subs, setSubs] = useState([]);
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [manageCred, setManageCred] = useState(null);
  const [assignTo, setAssignTo] = useState(null);

  const load = async () => {
    const [g, s, sb, u] = await Promise.all([
      api.get("/admin/groups"),
      api.get("/admin/services"),
      api.get("/admin/subscriptions"),
      api.get("/admin/users"),
    ]);
    setGroups(g.data); setServices(s.data); setSubs(sb.data); setUsers(u.data);
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return groups;
    return groups.filter((g) => [g.name, g.notes, services.find((s) => s.id === g.service_id)?.name].some((v) => String(v || "").toLowerCase().includes(needle)));
  }, [groups, q, services]);

  const del = async (id) => {
    if (!window.confirm("Hapus group? Subscriptions dalam group akan di-unlink (bukan dihapus).")) return;
    await api.delete(`/admin/groups/${id}`);
    toast.success("Group dihapus"); load();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="font-display font-bold text-2xl">Groups ({filtered.length}/{groups.length})</h2>
          <SearchInput value={q} onChange={setQ} placeholder="Cari nama group / layanan..." testid="groups-search" />
        </div>
        <button data-testid="admin-add-group" onClick={() => { setEditing(null); setShowModal(true); }} className="brutal-btn brutal-btn-red text-sm">
          <PlusCircle weight="bold" /> Tambah Group
        </button>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((g) => {
          const svc = services.find((s) => s.id === g.service_id);
          const totalHost = g.host_slots;
          const totalReg = g.regular_slots;
          const filledHost = g.filled_host || 0;
          const filledReg = g.filled_regular || 0;
          return (
            <div key={g.id} className="brutal p-5" data-testid={`group-card-${g.id}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="pd-tag" style={{ background: svc?.color, color: "#fff", borderColor: "#000" }}>{svc?.name || "?"}</div>
                  <div className="font-display font-bold text-xl mt-2">{g.name}</div>
                  <div className="mt-1 flex items-center gap-1 flex-wrap">
                    <span className={`pd-tag text-[10px] ${g.status === "paused" ? "bg-[#FFD60A]" : g.status === "expired" ? "bg-[#FF3B30] text-white" : "bg-[#34C759] text-white"}`}>{g.status || "active"}</span>
                    {g.expires_at && <span className="pd-tag text-[10px] bg-white">exp {new Date(g.expires_at).toLocaleDateString("id-ID", {day:"numeric",month:"short"})}</span>}
                  </div>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => { setEditing(g); setShowModal(true); }} data-testid={`group-edit-${g.id}`} className="brutal-sm p-2 bg-[#007AFF] text-white"><PencilSimple weight="bold" /></button>
                  <button onClick={() => del(g.id)} data-testid={`group-delete-${g.id}`} className="brutal-sm p-2 bg-[#FF3B30] text-white"><Trash weight="bold" /></button>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <SlotBar label="Host" filled={filledHost} total={totalHost} color="#FF3B30" />
                <SlotBar label="Regular" filled={filledReg} total={totalReg} color="#007AFF" />
              </div>
              <div className="mt-3 text-xs font-mono text-gray-600 flex items-center gap-1">
                <UsersThree size={14} /> {(g.members || []).length} member
              </div>
              {(g.members || []).length > 0 && (
                <ul className="mt-2 space-y-1 text-sm">
                  {g.members.slice(0, 6).map((m) => (
                    <li key={m.subscription_id} className="flex items-center justify-between border-b border-black/10 pb-1">
                      <span>{m.name || m.email}</span>
                      <span className={`pd-tag ${m.role === "host" ? "bg-[#FFD60A]" : "bg-white"}`}>{m.role}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex gap-2 mt-4">
                <button onClick={() => setAssignTo(g)} data-testid={`group-assign-${g.id}`} className="brutal-btn brutal-btn-yellow text-xs flex-1 justify-center">
                  <PlusCircle weight="bold" /> Assign user
                </button>
                {svc?.slug === "netflix" || g.credential || svc?.slug === "spotify" ? (
                  <button onClick={() => setManageCred(g)} data-testid={`group-credential-${g.id}`} className="brutal-btn brutal-btn-blue text-xs flex-1 justify-center">
                    <Key weight="bold" /> {g.credential ? "Edit login" : "Set login"}
                  </button>
                ) : (
                  <button onClick={() => setManageCred(g)} data-testid={`group-credential-${g.id}`} className="brutal-btn brutal-btn-white text-xs flex-1 justify-center">
                    <Key weight="bold" /> Login
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {filtered.length === 0 && (
          <div className="col-span-full brutal p-8 text-center text-gray-600">Belum ada group. Klik "Tambah Group" untuk buat.</div>
        )}
      </div>

      {showModal && <GroupModal group={editing} services={services} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
      {manageCred && <CredentialModal group={manageCred} onClose={() => setManageCred(null)} onSaved={load} />}
      {assignTo && <AssignModal group={assignTo} users={users} subs={subs} onClose={() => setAssignTo(null)} onSaved={load} />}
    </div>
  );
}

function SlotBar({ label, filled, total, color }) {
  const pct = total > 0 ? Math.round((filled / total) * 100) : 0;
  return (
    <div>
      <div className="text-xs font-mono uppercase text-gray-600">{label} {filled}/{total}</div>
      <div className="mt-1 h-2 border border-black bg-white overflow-hidden">
        <div className="h-full" style={{ width: `${pct}%`, background: color }}></div>
      </div>
    </div>
  );
}

function GroupModal({ group, services, onClose, onSaved }) {
  const [form, setForm] = useState({
    service_id: group?.service_id || "",
    name: group?.name || "",
    host_slots: group?.host_slots ?? 1,
    regular_slots: group?.regular_slots ?? 4,
    notes: group?.notes || "",
    status: group?.status || "active",
    expires_at: group?.expires_at ? String(group.expires_at).slice(0, 10) : "",
    active: group?.active !== false,
  });
  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...form,
        host_slots: Number(form.host_slots),
        regular_slots: Number(form.regular_slots),
        expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
      };
      if (group) await api.patch(`/admin/groups/${group.id}`, payload);
      else await api.post("/admin/groups", payload);
      toast.success("Group tersimpan"); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Modal onClose={onClose} title={group ? "Edit Group" : "Tambah Group"}>
      <form onSubmit={save} className="space-y-3" data-testid="group-modal-form">
        <F label="Layanan">
          <select required className="brutal-input" value={form.service_id} onChange={(e) => setForm({ ...form, service_id: e.target.value })} data-testid="gm-service">
            <option value="">Pilih...</option>
            {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </F>
        <F label="Nama group (mis: Netflix A)"><input required className="brutal-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="gm-name" /></F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Host slots"><input type="number" min="0" className="brutal-input" value={form.host_slots} onChange={(e) => setForm({ ...form, host_slots: e.target.value })} /></F>
          <F label="Regular slots"><input type="number" min="0" className="brutal-input" value={form.regular_slots} onChange={(e) => setForm({ ...form, regular_slots: e.target.value })} /></F>
        </div>
        <F label="Notes (opsional)"><textarea rows="2" className="brutal-input" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Status">
            <select className="brutal-input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="gm-status">
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="expired">Expired</option>
            </select>
          </F>
          <F label="Berakhir pada (opsional)"><input type="date" className="brutal-input" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} data-testid="gm-expires" /></F>
        </div>
        <label className="flex items-center gap-2"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Aktif (tampil di public availability)</label>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="gm-save">Simpan</button>
      </form>
    </Modal>
  );
}

function CredentialModal({ group, onClose, onSaved }) {
  const [form, setForm] = useState({ email: "", password: "", notes: "" });
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    api.get(`/admin/groups/${group.id}/credential`).then((r) => { if (r.data) setForm({ email: r.data.email || "", password: r.data.password || "", notes: r.data.notes || "" }); });
  }, [group.id]);
  const save = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.put(`/admin/groups/${group.id}/credential`, form);
      toast.success("Akses login tersimpan"); onSaved(); onClose();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  };
  const del = async () => {
    if (!window.confirm("Hapus akses login group ini?")) return;
    await api.delete(`/admin/groups/${group.id}/credential`);
    toast.success("Akses login dihapus"); onSaved(); onClose();
  };
  return (
    <Modal onClose={onClose} title={`Akses login — ${group.name}`}>
      <form onSubmit={save} className="space-y-3" data-testid="cred-modal-form">
        <p className="text-sm text-gray-700">Email + password ini akan tampil di dashboard semua anggota aktif group. Cocok untuk Netflix, Disney+, dll.</p>
        <F label="Email akun layanan"><input required type="email" className="brutal-input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="cred-email" /></F>
        <F label="Password"><input required className="brutal-input font-mono" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="cred-password" /></F>
        <F label="Catatan (opsional)"><textarea rows="2" className="brutal-input" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Contoh: Jangan ganti password. Pakai profile 'Guest'." /></F>
        <div className="flex gap-2">
          <button type="submit" disabled={loading} className="brutal-btn brutal-btn-red flex-1 justify-center" data-testid="cred-save">Simpan</button>
          <button type="button" onClick={del} className="brutal-btn brutal-btn-white"><Trash weight="bold" /></button>
        </div>
      </form>
    </Modal>
  );
}

function AssignModal({ group, users, subs, onClose, onSaved }) {
  const svcSubs = subs.filter((s) => s.service_id === group.service_id);
  const [subId, setSubId] = useState("");
  const assign = async (e) => {
    e.preventDefault();
    if (!subId) return;
    const s = subs.find((x) => x.id === subId);
    try {
      await api.patch(`/admin/subscriptions/${subId}`, {
        user_id: s.user_id, service_id: s.service_id, group_id: group.id,
        role: s.role, start_date: s.start_date, end_date: s.end_date,
        price: s.price, status: s.status,
      });
      toast.success("User di-assign ke group"); onSaved(); onClose();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Modal onClose={onClose} title={`Assign user ke ${group.name}`}>
      <form onSubmit={assign} className="space-y-3" data-testid="assign-modal">
        <p className="text-sm text-gray-700">Pilih subscription yang service-nya sama dengan group. Ubah group_id-nya otomatis.</p>
        <F label="Subscription">
          <select required className="brutal-input" value={subId} onChange={(e) => setSubId(e.target.value)} data-testid="assign-sub">
            <option value="">Pilih subscription...</option>
            {svcSubs.map((s) => <option key={s.id} value={s.id}>{s.user?.name} — {s.role} — {s.group_id ? `(sudah di group ${s.group_id.slice(-4)})` : "(belum di group)"}</option>)}
          </select>
        </F>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="assign-save">Assign</button>
      </form>
    </Modal>
  );
}
