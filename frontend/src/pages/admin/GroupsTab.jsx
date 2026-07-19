import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, Trash, PencilSimple, Key, UsersThree, Copy, CaretDown, CaretRight, Crown } from "@phosphor-icons/react";
import { Modal, F, SearchInput } from "./shared";
import DatePicker from "@/components/DatePicker";

export default function GroupsTab() {
  const [groups, setGroups] = useState([]);
  const [services, setServices] = useState([]);
  const [subs, setSubs] = useState([]);
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [prefillServiceId, setPrefillServiceId] = useState(null);
  const [editing, setEditing] = useState(null);
  const [manageCred, setManageCred] = useState(null);
  const [assignTo, setAssignTo] = useState(null);
  const [collapsed, setCollapsed] = useState({});

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

  // Bucket by service_id
  const byService = useMemo(() => {
    const map = new Map();
    for (const g of filtered) {
      const arr = map.get(g.service_id) || [];
      arr.push(g);
      map.set(g.service_id, arr);
    }
    return map;
  }, [filtered]);

  const del = async (id) => {
    if (!window.confirm("Hapus group? Subscriptions dalam group akan di-unlink (bukan dihapus).")) return;
    await api.delete(`/admin/groups/${id}`);
    toast.success("Group dihapus"); load();
  };

  const changeRole = async (member, newRole, groupId, serviceId) => {
    if (!window.confirm(`Ubah role user ini menjadi ${newRole.toUpperCase()}?`)) return;
    try {
      await api.patch(`/admin/subscriptions/${member.subscription_id}`, { role: newRole });
      toast.success("Role diubah");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const removeMember = async (member) => {
    if (!window.confirm(`Keluarkan ${member.name || member.email} dari group?`)) return;
    try {
      await api.patch(`/admin/subscriptions/${member.subscription_id}`, { group_id: null });
      toast.success("User dikeluarkan dari group");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const toggleCollapse = (sid) => setCollapsed({ ...collapsed, [sid]: !collapsed[sid] });
  const openCreate = (serviceId = null) => { setEditing(null); setPrefillServiceId(serviceId); setShowModal(true); };

  return (
    <div>
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="font-display font-bold text-2xl">Groups ({filtered.length}/{groups.length})</h2>
          <SearchInput value={q} onChange={setQ} placeholder="Cari nama group / layanan..." testid="groups-search" />
        </div>
        <button data-testid="admin-add-group" onClick={() => openCreate(null)} className="brutal-btn brutal-btn-red text-sm">
          <PlusCircle weight="bold" /> Tambah Group
        </button>
      </div>

      <div className="space-y-6" data-testid="groups-by-service">
        {services.map((svc) => {
          const grps = byService.get(svc.id) || [];
          const isCollapsed = collapsed[svc.id];
          const totalSlots = grps.reduce((a, g) => a + g.host_slots + g.regular_slots, 0);
          const filledSlots = grps.reduce((a, g) => a + (g.filled_host || 0) + (g.filled_regular || 0), 0);
          return (
            <div key={svc.id} className="brutal p-4" data-testid={`service-group-block-${svc.id}`}>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <button onClick={() => toggleCollapse(svc.id)} className="flex items-center gap-2 font-display font-black text-lg" data-testid={`service-collapse-${svc.id}`}>
                  {isCollapsed ? <CaretRight weight="bold" /> : <CaretDown weight="bold" />}
                  <span className="pd-tag" style={{ background: svc.color || "#000", color: "#fff", borderColor: "#000" }}>{svc.name}</span>
                  <span className="text-xs font-mono text-gray-600">{grps.length} grup • {filledSlots}/{totalSlots} slot</span>
                </button>
                <button onClick={() => openCreate(svc.id)} className="brutal-sm px-3 py-1 text-xs bg-[#FFD60A]" data-testid={`add-group-for-${svc.id}`}>
                  <PlusCircle weight="bold" /> Buat grup {svc.name}
                </button>
              </div>
              {!isCollapsed && (
                <div className="mt-4 grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {grps.length === 0 && <div className="col-span-full brutal-sm p-4 text-center text-gray-500 text-sm">Belum ada grup untuk layanan ini.</div>}
                  {grps.map((g) => (
                    <GroupCard
                      key={g.id}
                      group={g}
                      service={svc}
                      onEdit={() => { setEditing(g); setShowModal(true); }}
                      onDelete={() => del(g.id)}
                      onAssign={() => setAssignTo({ ...g, service_id: svc.id })}
                      onCred={() => setManageCred(g)}
                      onChangeRole={(m, r) => changeRole(m, r, g.id, svc.id)}
                      onRemoveMember={removeMember}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {services.length === 0 && <div className="brutal p-8 text-center text-gray-600">Belum ada layanan. Buat service dulu di tab Services.</div>}
      </div>

      {showModal && <GroupModal group={editing} prefillServiceId={prefillServiceId} services={services} onClose={() => { setShowModal(false); setPrefillServiceId(null); }} onSaved={() => { setShowModal(false); setPrefillServiceId(null); load(); }} />}
      {manageCred && <CredentialModal group={manageCred} onClose={() => setManageCred(null)} onSaved={load} />}
      {assignTo && <AssignModal group={assignTo} onClose={() => setAssignTo(null)} onSaved={load} />}
    </div>
  );
}

function GroupCard({ group: g, service: svc, onEdit, onDelete, onAssign, onCred, onChangeRole, onRemoveMember }) {
  const totalHost = g.host_slots;
  const totalReg = g.regular_slots;
  const filledHost = g.filled_host || 0;
  const filledReg = g.filled_regular || 0;
  const anyFree = filledHost < totalHost || filledReg < totalReg;
  return (
    <div className="brutal p-4 bg-white" data-testid={`group-card-${g.id}`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="font-display font-bold text-lg">{g.name}</div>
          <div className="mt-1 flex items-center gap-1 flex-wrap">
            <span className={`pd-tag text-[10px] ${g.status === "paused" ? "bg-[#FFD60A]" : g.status === "expired" ? "bg-[#FF3B30] text-white" : "bg-[#34C759] text-white"}`}>{g.status || "active"}</span>
            {g.auto_created && <span className="pd-tag text-[10px] bg-[#007AFF] text-white">Auto</span>}
            {g.expires_at && <span className="pd-tag text-[10px] bg-white">exp {new Date(g.expires_at).toLocaleDateString("id-ID", { day: "numeric", month: "short" })}</span>}
          </div>
        </div>
        <div className="flex gap-1">
          <button onClick={onEdit} data-testid={`group-edit-${g.id}`} className="brutal-sm p-2 bg-[#007AFF] text-white"><PencilSimple weight="bold" /></button>
          <button onClick={onDelete} data-testid={`group-delete-${g.id}`} className="brutal-sm p-2 bg-[#FF3B30] text-white"><Trash weight="bold" /></button>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <SlotBar label="Host" filled={filledHost} total={totalHost} />
        <SlotBar label="Regular" filled={filledReg} total={totalReg} />
      </div>
      {(g.members || []).length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {g.members.slice(0, 8).map((m) => (
            <li key={m.subscription_id} className="flex items-center justify-between gap-2 border-b border-black/10 pb-1" data-testid={`group-member-${m.subscription_id}`}>
              <span className="truncate">{m.name || m.email}</span>
              <div className="flex items-center gap-1">
                <span className={`pd-tag text-[10px] ${m.role === "host" ? "bg-[#FFD60A]" : "bg-white"}`}>{m.role}</span>
                {m.role === "regular" && (
                  <button onClick={() => onChangeRole(m, "host")} title="Jadikan host" data-testid={`promote-${m.subscription_id}`} className="brutal-sm p-1 bg-[#FFD60A]"><Crown weight="fill" size={12} /></button>
                )}
                {m.role === "host" && (
                  <button onClick={() => onChangeRole(m, "regular")} title="Turunkan jadi regular" data-testid={`demote-${m.subscription_id}`} className="brutal-sm p-1 bg-white"><Crown size={12} /></button>
                )}
                <button onClick={() => onRemoveMember(m)} title="Keluarkan dari group" data-testid={`remove-member-${m.subscription_id}`} className="brutal-sm p-1 bg-[#FF3B30] text-white"><Trash size={12} weight="bold" /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2 mt-3">
        <button onClick={onAssign} data-testid={`group-assign-${g.id}`} disabled={!anyFree} className={`brutal-btn text-xs flex-1 justify-center ${anyFree ? "brutal-btn-yellow" : "brutal-btn-white opacity-50"}`}>
          <PlusCircle weight="bold" /> {anyFree ? "Assign user" : "Penuh"}
        </button>
        <button onClick={onCred} data-testid={`group-credential-${g.id}`} className={`brutal-btn text-xs flex-1 justify-center ${g.credential ? "brutal-btn-blue" : "brutal-btn-white"}`}>
          <Key weight="bold" /> {g.credential ? "Edit login" : "Set login"}
        </button>
      </div>
    </div>
  );
}

function SlotBar({ label, filled, total }) {
  const pct = total > 0 ? Math.round((filled / total) * 100) : 0;
  const color = pct >= 100 ? "#FF3B30" : pct >= 75 ? "#FFD60A" : "#34C759";
  return (
    <div>
      <div className="text-xs font-mono uppercase text-gray-600">{label} <b>{filled}/{total}</b></div>
      <div className="mt-1 h-2 border border-black bg-white overflow-hidden">
        <div className="h-full" style={{ width: `${pct}%`, background: color }}></div>
      </div>
    </div>
  );
}

function GroupModal({ group, prefillServiceId, services, onClose, onSaved }) {
  const [form, setForm] = useState({
    service_id: group?.service_id || prefillServiceId || "",
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
          <F label="Berakhir pada (opsional)"><DatePicker value={form.expires_at} onChange={(v) => setForm({ ...form, expires_at: v })} testId="gm-expires" placeholder="Pilih tanggal berakhir" /></F>
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

function AssignModal({ group, onClose, onSaved }) {
  const [candidates, setCandidates] = useState([]);
  const [uid, setUid] = useState("");
  const [role, setRole] = useState("regular");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/admin/groups/unassigned-users?service_id=${group.service_id}`)
      .then((r) => setCandidates(r.data))
      .catch(() => setCandidates([]));
  }, [group.service_id]);

  const hostAvailable = (group.host_slots - (group.filled_host || 0)) > 0;
  const regAvailable = (group.regular_slots - (group.filled_regular || 0)) > 0;

  const assign = async (e) => {
    e.preventDefault();
    if (!uid) return toast.error("Pilih user dulu");
    const cand = candidates.find((c) => c.id === uid);
    setBusy(true);
    try {
      if (cand?.pending_sub_id) {
        // User already has a sub for this service without a group — just assign group + role
        await api.patch(`/admin/subscriptions/${cand.pending_sub_id}`, { group_id: group.id, role });
      } else {
        // Create a fresh subscription for this user in this group
        const svc = { price: 0 }; // price comes from service, but backend will accept
        await api.post(`/admin/subscriptions`, {
          user_id: uid,
          service_id: group.service_id,
          group_id: group.id,
          role,
          start_date: new Date().toISOString(),
          price: 0,
          status: "active",
          duration_months: 1,
        });
      }
      toast.success(`User assigned sebagai ${role.toUpperCase()}`);
      onSaved(); onClose();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <Modal onClose={onClose} title={`Assign user ke ${group.name}`}>
      <form onSubmit={assign} className="space-y-3" data-testid="assign-modal">
        <div className="brutal-sm bg-[#FFD60A]/40 p-3 text-sm">
          Hanya user yang <b>belum masuk grup layanan ini</b> yang tampil di daftar ({candidates.length} kandidat).
        </div>
        <F label="Role">
          <div className="flex gap-2">
            <label className="flex items-center gap-2">
              <input type="radio" name="role" value="regular" checked={role === "regular"} onChange={() => setRole("regular")} disabled={!regAvailable} data-testid="assign-role-regular" />
              Regular {regAvailable ? `(${group.regular_slots - (group.filled_regular || 0)} slot)` : "(penuh)"}
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="role" value="host" checked={role === "host"} onChange={() => setRole("host")} disabled={!hostAvailable} data-testid="assign-role-host" />
              Host {hostAvailable ? `(${group.host_slots - (group.filled_host || 0)} slot)` : "(penuh)"}
            </label>
          </div>
        </F>
        <F label={`Pilih user (${candidates.length})`}>
          <select required className="brutal-input" value={uid} onChange={(e) => setUid(e.target.value)} data-testid="assign-user">
            <option value="">Pilih user...</option>
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} — {c.email}{c.has_pending_sub ? " ✓ sudah bayar" : ""}
              </option>
            ))}
          </select>
        </F>
        <button type="submit" disabled={busy || !uid} className="brutal-btn brutal-btn-red w-full justify-center" data-testid="assign-save">
          {busy ? "Mengassign..." : `Assign sebagai ${role.toUpperCase()}`}
        </button>
      </form>
    </Modal>
  );
}

