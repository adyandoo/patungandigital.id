import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, PencilSimple, Trash, Megaphone, X, Warning, Info, SortAscending } from "@phosphor-icons/react";
import { Modal, F } from "./shared";

const SEVERITY = {
  info: { bg: "bg-[#007AFF]", fg: "text-white", label: "Info" },
  warning: { bg: "bg-[#FFD60A]", fg: "text-black", label: "Warning" },
  critical: { bg: "bg-[#FF3B30]", fg: "text-white", label: "Critical" },
};

const SORT_OPTIONS = [
  { key: "created_at_desc", label: "Terbaru" },
  { key: "created_at_asc", label: "Terlama" },
  { key: "severity", label: "Severity (critical dulu)" },
  { key: "title_asc", label: "Judul A-Z" },
  { key: "expires_at", label: "Terdekat expire" },
];

const SEV_ORDER = { critical: 0, warning: 1, info: 2 };

export default function AnnouncementsTab() {
  const [items, setItems] = useState([]);
  const [services, setServices] = useState([]);
  const [editing, setEditing] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [sortBy, setSortBy] = useState("created_at_desc");

  const load = () => {
    api.get("/admin/announcements").then((r) => setItems(r.data)).catch(() => setItems([]));
    api.get("/services").then((r) => setServices(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const sorted = useMemo(() => {
    const arr = [...items];
    arr.sort((a, b) => {
      if (sortBy === "severity") return (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9);
      if (sortBy === "title_asc") return (a.title || "").localeCompare(b.title || "", "id");
      if (sortBy === "expires_at") {
        const va = a.expires_at ? new Date(a.expires_at).getTime() : Infinity;
        const vb = b.expires_at ? new Date(b.expires_at).getTime() : Infinity;
        return va - vb;
      }
      const va = new Date(a.created_at || 0).getTime();
      const vb = new Date(b.created_at || 0).getTime();
      return sortBy === "created_at_asc" ? va - vb : vb - va;
    });
    return arr;
  }, [items, sortBy]);

  const del = async (a) => {
    if (!window.confirm(`Hapus pengumuman "${a.title}"?`)) return;
    try { await api.delete(`/admin/announcements/${a.id}`); toast.success("Pengumuman dihapus."); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div data-testid="announcements-tab">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <h2 className="font-display font-bold text-2xl flex items-center gap-2"><Megaphone weight="duotone" /> Pengumuman</h2>
        <div className="flex gap-2 flex-wrap items-center">
          <label className="brutal-sm bg-white px-2 py-1 flex items-center gap-2 text-xs font-mono">
            <SortAscending size={14} />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="bg-transparent outline-none uppercase"
              data-testid="ann-sort"
            >
              {SORT_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
          <button onClick={() => { setEditing(null); setShowModal(true); }} className="brutal-btn brutal-btn-red text-sm" data-testid="announcement-add">
            <PlusCircle weight="bold" /> Buat pengumuman
          </button>
        </div>
      </div>

      {sorted.length === 0 && <div className="brutal p-8 text-center text-gray-600">Belum ada pengumuman.</div>}

      <div className="space-y-3">
        {sorted.map((a) => {
          const s = SEVERITY[a.severity] || SEVERITY.info;
          const expired = a.expires_at && new Date(a.expires_at).getTime() < Date.now();
          const targetServices = a.target === "service_ids"
            ? services.filter((sv) => (a.service_ids || []).includes(sv.id)).map((sv) => sv.name).join(", ") || "-"
            : "Semua user";
          return (
            <div key={a.id} className="brutal p-4" data-testid={`admin-announcement-${a.id}`}>
              <div className="flex items-start gap-3 flex-wrap">
                <span className={`brutal-sm px-2 py-1 text-xs font-mono uppercase ${s.bg} ${s.fg}`}>{s.label}</span>
                <div className="flex-1 min-w-[200px]">
                  <div className="font-display font-bold">{a.title}</div>
                  <div className="text-sm text-gray-700 mt-1 whitespace-pre-line">{a.body}</div>
                  <div className="text-xs font-mono text-gray-600 mt-2 flex flex-wrap gap-3">
                    <span>Target: <b>{targetServices}</b></span>
                    <span>Dismissed: <b>{a.dismissed_by_count || 0}</b></span>
                    {a.expires_at && <span>Expire: <b className={expired ? "text-red-700" : ""}>{new Date(a.expires_at).toLocaleString("id-ID")}</b></span>}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => { setEditing(a); setShowModal(true); }} className="brutal-sm px-2 py-1 text-xs bg-[#007AFF] text-white" data-testid={`announcement-edit-${a.id}`}><PencilSimple weight="bold" /></button>
                  <button onClick={() => del(a)} className="brutal-sm px-2 py-1 text-xs bg-[#FF3B30] text-white" data-testid={`announcement-delete-${a.id}`}><Trash weight="bold" /></button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {showModal && <AnnouncementModal ann={editing} services={services} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function AnnouncementModal({ ann, services, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: ann?.title || "",
    body: ann?.body || "",
    severity: ann?.severity || "info",
    target: ann?.target || "all",
    service_ids: ann?.service_ids || [],
    expires_at: ann?.expires_at ? new Date(ann.expires_at).toISOString().slice(0, 16) : "",
  });

  const toggleService = (id) => {
    setForm({ ...form, service_ids: form.service_ids.includes(id) ? form.service_ids.filter((x) => x !== id) : [...form.service_ids, id] });
  };

  const save = async (e) => {
    e.preventDefault();
    if (form.target === "service_ids" && form.service_ids.length === 0) {
      return toast.error("Pilih minimal 1 layanan atau ganti target ke 'Semua user'.");
    }
    const payload = {
      title: form.title,
      body: form.body,
      severity: form.severity,
      target: form.target,
      service_ids: form.target === "service_ids" ? form.service_ids : [],
      expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
    };
    try {
      if (ann) await api.patch(`/admin/announcements/${ann.id}`, payload);
      else await api.post("/admin/announcements", payload);
      toast.success(ann ? "Pengumuman diperbarui." : "Pengumuman dikirim.");
      onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Modal onClose={onClose} title={ann ? "Edit Pengumuman" : "Buat Pengumuman"}>
      <form onSubmit={save} className="space-y-3" data-testid="announcement-modal-form">
        <F label="Judul *"><input required maxLength={140} className="brutal-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="ann-title" /></F>
        <F label="Isi *"><textarea required rows={5} maxLength={2000} className="brutal-input" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} data-testid="ann-body" /></F>
        <div className="grid md:grid-cols-2 gap-3">
          <F label="Severity">
            <select className="brutal-input" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })} data-testid="ann-severity">
              <option value="info">Info (biru)</option>
              <option value="warning">Warning (kuning)</option>
              <option value="critical">Critical (merah)</option>
            </select>
          </F>
          <F label="Expire (opsional)">
            <input type="datetime-local" className="brutal-input" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} data-testid="ann-expires-at" />
          </F>
        </div>
        <F label="Target">
          <div className="flex gap-2 flex-wrap">
            <label className="flex items-center gap-2"><input type="radio" name="target" value="all" checked={form.target === "all"} onChange={() => setForm({ ...form, target: "all" })} data-testid="ann-target-all" /> Semua user</label>
            <label className="flex items-center gap-2"><input type="radio" name="target" value="service_ids" checked={form.target === "service_ids"} onChange={() => setForm({ ...form, target: "service_ids" })} data-testid="ann-target-services" /> User layanan tertentu</label>
          </div>
        </F>
        {form.target === "service_ids" && (
          <F label={`Pilih layanan (${form.service_ids.length} dipilih)`}>
            <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto brutal-sm bg-white p-3">
              {services.map((s) => (
                <label key={s.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.service_ids.includes(s.id)} onChange={() => toggleService(s.id)} data-testid={`ann-service-${s.id}`} />
                  {s.name}
                </label>
              ))}
            </div>
          </F>
        )}
        <button type="submit" className="brutal-btn brutal-btn-red w-full justify-center" data-testid="ann-save">
          {ann ? "Simpan perubahan" : "Kirim pengumuman"}
        </button>
      </form>
    </Modal>
  );
}
