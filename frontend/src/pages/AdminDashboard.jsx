import { useEffect, useMemo, useState } from "react";
import api, { rupiah, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  Users, PlusCircle, Trash, PencilSimple, PaperPlaneTilt, Receipt,
  Storefront, Ticket, GearSix, Eye, X, Image as ImageIcon,
  ClockCounterClockwise, DownloadSimple, CheckSquare, Lightning,
  MagnifyingGlass,
} from "@phosphor-icons/react";

const TABS = [
  { id: "overview", label: "Overview", icon: <GearSix weight="duotone" /> },
  { id: "users", label: "Users", icon: <Users weight="duotone" /> },
  { id: "services", label: "Services", icon: <Storefront weight="duotone" /> },
  { id: "subscriptions", label: "Subscriptions", icon: <Ticket weight="duotone" /> },
  { id: "payments", label: "Payments", icon: <Receipt weight="duotone" /> },
  { id: "reminder", label: "Reminder", icon: <PaperPlaneTilt weight="duotone" /> },
  { id: "activity", label: "Activity", icon: <ClockCounterClockwise weight="duotone" /> },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState({});

  useEffect(() => { api.get("/admin/stats").then((r) => setStats(r.data)).catch(() => {}); }, [tab]);

  return (
    <div className="px-6 md:px-12 py-10">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <span className="pd-tag bg-[#FFD60A]">Admin</span>
          <h1 className="font-display font-black text-4xl md:text-5xl mt-3">Kontrol pusat</h1>
          <p className="text-gray-700 mt-1">Kelola user, layanan, langganan, dan pembayaran.</p>
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="admin-stats">
        <Stat label="Users" value={stats.users || 0} color="#007AFF" />
        <Stat label="Services" value={stats.services || 0} color="#FF3B30" />
        <Stat label="Active Subs" value={stats.active_subscriptions || 0} color="#34C759" />
        <Stat label="Pending Payments" value={stats.pending_payments || 0} color="#FFD60A" />
      </div>

      <div className="mt-8 flex gap-2 border-b-2 border-black overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.id} data-testid={`admin-tab-${t.id}`} onClick={() => setTab(t.id)} className={`px-4 py-3 font-display font-bold flex items-center gap-2 border-2 border-black border-b-0 -mb-[2px] whitespace-nowrap ${tab === t.id ? "bg-[#FFD60A]" : "bg-white"}`}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      <div className="mt-8">
        {tab === "overview" && <Overview />}
        {tab === "users" && <UsersTab />}
        {tab === "services" && <ServicesTab />}
        {tab === "subscriptions" && <SubscriptionsTab />}
        {tab === "payments" && <PaymentsTab />}
        {tab === "reminder" && <ReminderTab />}
        {tab === "activity" && <ActivityTab />}
      </div>
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div className="brutal p-5">
      <div className="w-3 h-3" style={{ background: color }}></div>
      <div className="font-mono text-xs uppercase text-gray-600 mt-3">{label}</div>
      <div className="font-display font-black text-4xl mt-1">{value}</div>
    </div>
  );
}

function Overview() {
  const [ana, setAna] = useState(null);
  useEffect(() => { api.get("/admin/analytics").then((r) => setAna(r.data)).catch(() => {}); }, []);
  const totals = ana?.totals || {};
  return (
    <div className="space-y-6">
      <div className="brutal p-8">
        <h2 className="font-display font-bold text-2xl">Selamat datang, Admin.</h2>
        <p className="mt-2 text-gray-700">Gunakan tab di atas untuk mengelola seluruh platform. Semua CRUD user, service, subscription, dan pengingat pembayaran ada di sini.</p>
      </div>

      {/* Analytics */}
      <div className="grid md:grid-cols-3 gap-6">
        <BigMetric label="Total pendapatan (paid)" value={rupiah(totals.total_revenue_paid || 0)} color="#34C759" />
        <BigMetric label="Pembayaran lunas" value={totals.paid_count || 0} color="#007AFF" />
        <BigMetric label="Rata-rata pembayaran" value={rupiah(Math.round(totals.avg_payment || 0))} color="#FFD60A" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="brutal p-6 lg:col-span-2" data-testid="analytics-monthly-chart">
          <div className="font-display font-bold text-xl mb-4">Pendapatan bulanan (12 bulan)</div>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <LineChart data={ana?.monthly || []} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#0A0A0A" strokeDasharray="0" strokeOpacity={0.1} />
                <XAxis dataKey="label" stroke="#0A0A0A" tick={{ fontFamily: "Space Mono", fontSize: 11 }} />
                <YAxis stroke="#0A0A0A" tick={{ fontFamily: "Space Mono", fontSize: 11 }} tickFormatter={(v) => `${(v/1000)|0}k`} />
                <Tooltip contentStyle={{ border: "2px solid #0A0A0A", borderRadius: 0, boxShadow: "4px 4px 0 #0A0A0A", background: "#fff", fontFamily: "IBM Plex Sans" }} formatter={(v) => rupiah(v)} />
                <Line type="stepAfter" dataKey="revenue" stroke="#FF3B30" strokeWidth={3} dot={{ fill: "#0A0A0A", r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="brutal p-6" data-testid="analytics-service-chart">
          <div className="font-display font-bold text-xl mb-4">Revenue per layanan</div>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={ana?.by_service || []} layout="vertical" margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid stroke="#0A0A0A" strokeOpacity={0.1} />
                <XAxis type="number" stroke="#0A0A0A" tick={{ fontFamily: "Space Mono", fontSize: 11 }} tickFormatter={(v) => `${(v/1000)|0}k`} />
                <YAxis dataKey="service" type="category" stroke="#0A0A0A" tick={{ fontFamily: "Space Mono", fontSize: 11 }} width={80} />
                <Tooltip contentStyle={{ border: "2px solid #0A0A0A", borderRadius: 0, boxShadow: "4px 4px 0 #0A0A0A", background: "#fff" }} formatter={(v) => rupiah(v)} />
                <Bar dataKey="revenue" fill="#007AFF" stroke="#0A0A0A" strokeWidth={2} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Note title="Auto Scheduler (ACTIVE)" body="Background scheduler jalan setiap 1 jam, otomatis kirim reminder untuk tagihan yang jatuh tempo dalam H-N (sesuai konfigurasi). Trigger manual via tab Reminder → Run scheduler now." />
        <Note title="Activity Log" body="Semua aksi admin (create/delete/bulk/send reminder/scheduler run/export) tercatat di tab Activity." />
        <Note title="Payment Gateway (Xendit)" body="Isi XENDIT_API_KEY di backend/.env untuk invoice otomatis. Webhook siap di /api/webhooks/xendit — pasang di Xendit dashboard dengan XENDIT_WEBHOOK_TOKEN." />
        <Note title="Reminder Email + WhatsApp" body="Isi SENDGRID_API_KEY dan TWILIO_ACCOUNT_SID/AUTH_TOKEN untuk mengaktifkan notifikasi. Tanpa key, pengiriman berjalan dalam mode MOCKED (dicatat di log)." />
      </div>
    </div>
  );
}

function BigMetric({ label, value, color }) {
  return (
    <div className="brutal p-6">
      <div className="w-3 h-3" style={{ background: color }}></div>
      <div className="font-mono text-xs uppercase text-gray-600 mt-3">{label}</div>
      <div className="font-display font-black text-3xl mt-1">{value}</div>
    </div>
  );
}
function Note({ title, body }) {
  return (
    <div className="brutal-sm bg-[#FFD60A]/40 p-5">
      <div className="font-display font-bold">{title}</div>
      <p className="text-sm text-gray-800 mt-1">{body}</p>
    </div>
  );
}

/* ---------- Users ---------- */
function UsersTab() {
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
      [u.name, u.email, u.username, u.whatsapp, u.role].some((v) => String(v || "").toLowerCase().includes(needle))
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
          <SearchInput value={q} onChange={setQ} placeholder="Cari nama, email, WA..." testid="users-search" />
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
              {["Nama", "Email", "Username", "WhatsApp", "Role", "Aksi"].map((h) => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs">{h}</th>)}
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
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-600">Tidak ada hasil.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {showModal && <UserModal user={editing} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function SearchInput({ value, onChange, placeholder, testid }) {
  return (
    <div className="brutal-sm bg-white flex items-center gap-2 px-3 py-2">
      <MagnifyingGlass weight="bold" size={16} />
      <input
        data-testid={testid}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="border-none outline-none w-56 text-sm bg-transparent"
      />
      {value && (
        <button onClick={() => onChange("")} className="text-gray-500 hover:text-black" title="Clear">
          <X weight="bold" size={14} />
        </button>
      )}
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

/* ---------- Services ---------- */
function ServicesTab() {
  const [services, setServices] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [managePlans, setManagePlans] = useState(null);

  const load = () => api.get("/admin/services").then((r) => setServices(r.data));
  useEffect(() => { load(); }, []);

  const del = async (id) => {
    if (!window.confirm("Hapus service ini?")) return;
    await api.delete(`/admin/services/${id}`);
    toast.success("Service dihapus"); load();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="font-display font-bold text-2xl">Services ({services.length})</h2>
        <button data-testid="admin-add-service" className="brutal-btn brutal-btn-red" onClick={() => { setEditing(null); setShowModal(true); }}>
          <PlusCircle weight="bold" /> Tambah Service
        </button>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {services.map((s) => (
          <div key={s.id} className="brutal overflow-hidden" data-testid={`service-item-${s.id}`}>
            <div className="h-24 border-b-2 border-black" style={{ background: s.color }}></div>
            <div className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-display font-bold text-xl">{s.name}</div>
                  <div className="pd-tag mt-1">{s.slug}</div>
                </div>
                <span className={`pd-tag ${s.active ? "bg-[#34C759] text-white" : "bg-gray-200"}`}>{s.active ? "aktif" : "nonaktif"}</span>
              </div>
              <div className="mt-3 font-display font-black text-2xl">{rupiah(s.price_regular)}<span className="text-sm font-normal">/bln</span></div>
              <div className="text-xs text-gray-600">min {s.min_duration_months} bulan</div>
              <div className="flex gap-2 mt-4 flex-wrap">
                <button data-testid={`service-edit-${s.id}`} onClick={() => { setEditing(s); setShowModal(true); }} className="brutal-btn brutal-btn-blue text-xs">Edit</button>
                <button data-testid={`service-plans-${s.id}`} onClick={() => setManagePlans(s)} className="brutal-btn brutal-btn-yellow text-xs">Plans</button>
                <button data-testid={`service-delete-${s.id}`} onClick={() => del(s.id)} className="brutal-btn brutal-btn-red text-xs"><Trash /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
      {showModal && <ServiceModal service={editing} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
      {managePlans && <PlansModal service={managePlans} onClose={() => setManagePlans(null)} />}
    </div>
  );
}

function ServiceModal({ service, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: service?.name || "",
    slug: service?.slug || "",
    description: service?.description || "",
    price_regular: service?.price_regular || 0,
    price_host: service?.price_host || 0,
    min_duration_months: service?.min_duration_months || 1,
    logo_url: service?.logo_url || "",
    color: service?.color || "#FF3B30",
    active: service?.active !== false,
  });
  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form, price_regular: Number(form.price_regular), price_host: Number(form.price_host), min_duration_months: Number(form.min_duration_months) };
      if (service) await api.patch(`/admin/services/${service.id}`, payload);
      else await api.post("/admin/services", payload);
      toast.success("Service tersimpan"); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Modal onClose={onClose} title={service ? "Edit Service" : "Tambah Service"}>
      <form onSubmit={save} className="space-y-3" data-testid="service-modal-form">
        <div className="grid grid-cols-2 gap-3">
          <F label="Nama"><input required className="brutal-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="sm-name" /></F>
          <F label="Slug"><input required className="brutal-input" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} data-testid="sm-slug" /></F>
          <F label="Harga regular (Rp)"><input type="number" className="brutal-input" value={form.price_regular} onChange={(e) => setForm({ ...form, price_regular: e.target.value })} /></F>
          <F label="Harga host (Rp)"><input type="number" className="brutal-input" value={form.price_host} onChange={(e) => setForm({ ...form, price_host: e.target.value })} /></F>
          <F label="Min bulan"><input type="number" className="brutal-input" value={form.min_duration_months} onChange={(e) => setForm({ ...form, min_duration_months: e.target.value })} /></F>
          <F label="Warna"><input type="color" className="brutal-input h-11" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} /></F>
        </div>
        <F label="Logo URL"><input className="brutal-input" value={form.logo_url} onChange={(e) => setForm({ ...form, logo_url: e.target.value })} placeholder="https://..." /></F>
        <F label="Deskripsi"><textarea rows="3" className="brutal-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></F>
        <label className="flex items-center gap-2"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Aktif</label>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="sm-save">Simpan</button>
      </form>
    </Modal>
  );
}

function PlansModal({ service, onClose }) {
  const [plans, setPlans] = useState([]);
  const [form, setForm] = useState({ name: "", host_slots: 1, regular_slots: 5, notes: "" });
  const load = () => api.get(`/admin/services/${service.id}/plans`).then((r) => setPlans(r.data));
  useEffect(() => { load(); }, []);
  const create = async (e) => {
    e.preventDefault();
    await api.post(`/admin/services/${service.id}/plans`, { ...form, host_slots: Number(form.host_slots), regular_slots: Number(form.regular_slots) });
    toast.success("Plan ditambahkan"); setForm({ name: "", host_slots: 1, regular_slots: 5, notes: "" }); load();
  };
  const del = async (pid) => {
    await api.delete(`/admin/plans/${pid}`);
    toast.success("Plan dihapus"); load();
  };
  return (
    <Modal onClose={onClose} title={`Plans — ${service.name}`}>
      <div className="space-y-2 mb-4">
        {plans.map((p) => (
          <div key={p.id} className="brutal-sm p-3 flex justify-between items-center bg-white">
            <div>
              <div className="font-semibold">{p.name}</div>
              <div className="text-xs text-gray-600">{p.host_slots} host + {p.regular_slots} regular</div>
            </div>
            <button className="brutal-sm p-2 bg-[#FF3B30] text-white" onClick={() => del(p.id)}><Trash /></button>
          </div>
        ))}
      </div>
      <form onSubmit={create} className="space-y-2 border-t-2 border-black pt-4">
        <F label="Nama plan"><input required className="brutal-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></F>
        <div className="grid grid-cols-2 gap-2">
          <F label="Host slots"><input type="number" className="brutal-input" value={form.host_slots} onChange={(e) => setForm({ ...form, host_slots: e.target.value })} /></F>
          <F label="Regular slots"><input type="number" className="brutal-input" value={form.regular_slots} onChange={(e) => setForm({ ...form, regular_slots: e.target.value })} /></F>
        </div>
        <button type="submit" className="brutal-btn brutal-btn-blue">Tambah plan</button>
      </form>
    </Modal>
  );
}

/* ---------- Subscriptions ---------- */
function SubscriptionsTab() {
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
            <tr>{["User", "Service", "Role", "Mulai", "Harga", "Status", "Aksi"].map((h) => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs">{h}</th>)}</tr>
          </thead>
          <tbody data-testid="subs-table">
            {filtered.map((s) => (
              <tr key={s.id} className="border-t-2 border-black">
                <td className="px-4 py-3 font-semibold">{s.user?.name || "?"}</td>
                <td className="px-4 py-3">{s.service?.name}</td>
                <td className="px-4 py-3"><span className="pd-tag">{s.role}</span></td>
                <td className="px-4 py-3">{s.start_date ? new Date(s.start_date).toLocaleDateString("id-ID") : "-"}</td>
                <td className="px-4 py-3">{rupiah(s.price)}</td>
                <td className="px-4 py-3"><span className="pd-tag">{s.status}</span></td>
                <td className="px-4 py-3">
                  <button onClick={() => del(s.id)} className="brutal-sm p-2 bg-[#FF3B30] text-white"><Trash /></button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-600">Tidak ada hasil.</td></tr>
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
    user_id: "", service_id: "", role: "regular",
    start_date: new Date().toISOString().slice(0, 10),
    end_date: "", price: 0, status: "active",
  });
  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...form, price: Number(form.price),
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
          <select required className="brutal-input" value={form.service_id} onChange={(e) => { const svc = services.find((s) => s.id === e.target.value); setForm({ ...form, service_id: e.target.value, price: svc?.price_regular || 0 }); }} data-testid="submod-service">
            <option value="">Pilih service...</option>
            {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Role">
            <select className="brutal-input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="regular">Regular</option><option value="host">Host</option>
            </select>
          </F>
          <F label="Harga (Rp)"><input type="number" className="brutal-input" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></F>
          <F label="Mulai"><input type="date" className="brutal-input" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></F>
          <F label="Sampai (opsional)"><input type="date" className="brutal-input" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></F>
        </div>
        <button type="submit" className="brutal-btn brutal-btn-red" data-testid="submod-save">Simpan</button>
      </form>
    </Modal>
  );
}

/* ---------- Payments ---------- */
function PaymentsTab() {
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
                <td className="px-4 py-3">{rupiah(p.amount)}</td>
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
        <button type="submit" className="brutal-btn brutal-btn-red">Buat tagihan</button>
      </form>
    </Modal>
  );
}

/* ---------- Reminder Config ---------- */
function ReminderTab() {
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
        enable_whatsapp: !!cfg.enable_whatsapp,
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
        <p className="text-sm text-gray-700 mt-1">Scheduler otomatis jalan setiap 1 jam & kirim reminder untuk tagihan H-N sebelum jatuh tempo (yang belum diingatkan dalam 24 jam terakhir).</p>
        <div className="mt-6 space-y-4">
          <F label="Kirim reminder H- (hari)"><input type="number" className="brutal-input" value={cfg.days_before_due} onChange={(e) => setCfg({ ...cfg, days_before_due: e.target.value })} /></F>
          <label className="flex items-center gap-2"><input type="checkbox" checked={cfg.enable_email} onChange={(e) => setCfg({ ...cfg, enable_email: e.target.checked })} /> Aktifkan Email (SendGrid)</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={cfg.enable_whatsapp} onChange={(e) => setCfg({ ...cfg, enable_whatsapp: e.target.checked })} /> Aktifkan WhatsApp (Twilio)</label>
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

/* ---------- Activity Log ---------- */
function ActivityTab() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/logs?limit=200");
      setLogs(data.logs); setTotal(data.total);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const actionColor = (a) => {
    if (a.startsWith("delete")) return "bg-[#FF3B30] text-white";
    if (a.startsWith("create")) return "bg-[#34C759] text-white";
    if (a.startsWith("bulk")) return "bg-[#FFD60A]";
    if (a.startsWith("export")) return "bg-white";
    if (a.startsWith("scheduler")) return "bg-[#007AFF] text-white";
    if (a === "send_reminder") return "bg-[#FFD60A]";
    return "bg-gray-100";
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div>
          <h2 className="font-display font-bold text-2xl">Activity Log</h2>
          <p className="text-sm text-gray-700">Total {total} aksi tercatat. Menampilkan 200 terbaru.</p>
        </div>
        <button onClick={load} className="brutal-btn brutal-btn-white text-sm" data-testid="activity-refresh">Refresh</button>
      </div>
      {loading ? (
        <div className="brutal p-8 text-center text-gray-600">Memuat...</div>
      ) : logs.length === 0 ? (
        <div className="brutal p-8 text-center text-gray-600">Belum ada aktivitas.</div>
      ) : (
        <div className="brutal overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-black text-white">
              <tr>{["Waktu", "Aktor", "Aksi", "Target", "Detail"].map((h) => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs">{h}</th>)}</tr>
            </thead>
            <tbody data-testid="activity-table">
              {logs.map((l) => (
                <tr key={l.id} className="border-t-2 border-black">
                  <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">{new Date(l.created_at).toLocaleString("id-ID")}</td>
                  <td className="px-4 py-3">
                    <div className="font-semibold">{l.actor_name || "system"}</div>
                    <div className="text-xs text-gray-600">{l.actor_email}</div>
                  </td>
                  <td className="px-4 py-3"><span className={`px-2 py-1 border-2 border-black font-mono text-xs uppercase inline-block ${actionColor(l.action)}`}>{l.action}</span></td>
                  <td className="px-4 py-3 font-mono text-xs">{l.target || "-"}</td>
                  <td className="px-4 py-3 text-xs text-gray-700">
                    {l.meta && Object.keys(l.meta).length > 0 ? (
                      <div className="max-w-md">
                        {Object.entries(l.meta).slice(0, 4).map(([k, v]) => (
                          <div key={k}><span className="font-mono text-gray-500">{k}:</span> {String(v)}</div>
                        ))}
                      </div>
                    ) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Shared ---------- */
function Modal({ children, onClose, title }) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white brutal-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="border-b-2 border-black p-4 flex items-center justify-between sticky top-0 bg-[#FFD60A]">
          <div className="font-display font-black text-xl">{title}</div>
          <button onClick={onClose} data-testid="modal-close"><X weight="bold" size={24} /></button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

function F({ label, children }) {
  return (
    <label className="block">
      <div className="font-mono text-xs uppercase mb-2">{label}</div>
      {children}
    </label>
  );
}
