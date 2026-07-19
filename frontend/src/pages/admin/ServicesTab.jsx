import { useEffect, useState } from "react";
import api, { rupiah, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PlusCircle, Trash } from "@phosphor-icons/react";
import { Modal, F } from "./shared";

export default function ServicesTab() {
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
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
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
