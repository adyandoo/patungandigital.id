import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Star, CheckCircle, X, Trash, ChatCircleDots, SortAscending } from "@phosphor-icons/react";
import Avatar from "@/components/Avatar";

const STATUS_ORDER = ["pending", "approved", "rejected"];
const SORT_OPTIONS = [
  { key: "created_at_desc", label: "Terbaru" },
  { key: "created_at_asc", label: "Terlama" },
  { key: "rating_desc", label: "Rating ↓" },
  { key: "rating_asc", label: "Rating ↑" },
  { key: "name_asc", label: "Nama A-Z" },
];

export default function TestimonialsTab() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [sortBy, setSortBy] = useState("created_at_desc");

  const load = () => {
    const q = filter === "all" ? "" : `?status=${filter}`;
    api.get(`/admin/testimonials${q}`).then((r) => setItems(r.data)).catch(() => setItems([]));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

  const sorted = useMemo(() => {
    const arr = [...items];
    const [k, dir] = sortBy.startsWith("rating") ? ["rating", sortBy.endsWith("desc") ? -1 : 1]
      : sortBy.startsWith("name") ? ["name", sortBy.endsWith("desc") ? -1 : 1]
      : ["created_at", sortBy.endsWith("desc") ? -1 : 1];
    arr.sort((a, b) => {
      const va = k === "name" ? (a.user?.name || "") : k === "created_at" ? new Date(a.created_at || 0).getTime() : (a[k] || 0);
      const vb = k === "name" ? (b.user?.name || "") : k === "created_at" ? new Date(b.created_at || 0).getTime() : (b[k] || 0);
      if (typeof va === "string") return va.localeCompare(vb, "id") * dir;
      return (va - vb) * dir;
    });
    return arr;
  }, [items, sortBy]);

  const setStatus = async (t, status) => {
    try {
      await api.patch(`/admin/testimonials/${t.id}`, { status });
      toast.success(`Testimoni ${status === "approved" ? "disetujui — tayang di homepage" : status === "rejected" ? "ditolak" : "dikembalikan ke pending"}.`);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const del = async (t) => {
    if (!window.confirm("Hapus testimoni ini permanen?")) return;
    try { await api.delete(`/admin/testimonials/${t.id}`); toast.success("Testimoni dihapus."); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div data-testid="testimonials-tab">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <h2 className="font-display font-bold text-2xl flex items-center gap-2"><ChatCircleDots weight="duotone" /> Testimoni</h2>
        <div className="flex gap-2 flex-wrap items-center">
          <div className="flex gap-2">
            {["all", ...STATUS_ORDER].map((s) => (
              <button key={s} onClick={() => setFilter(s)}
                className={`brutal-sm px-3 py-1 text-xs font-mono uppercase ${filter === s ? "bg-black text-white" : "bg-white"}`}
                data-testid={`testimoni-filter-${s}`}>
                {s}
              </button>
            ))}
          </div>
          <label className="brutal-sm bg-white px-2 py-1 flex items-center gap-2 text-xs font-mono">
            <SortAscending size={14} />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="bg-transparent outline-none uppercase"
              data-testid="testimoni-sort"
            >
              {SORT_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
        </div>
      </div>

      {sorted.length === 0 && <div className="brutal p-8 text-center text-gray-600">Kosong.</div>}
      <div className="grid md:grid-cols-2 gap-4">
        {sorted.map((t) => (
          <div key={t.id} className="brutal p-5" data-testid={`admin-testimoni-${t.id}`}>
            <div className="flex items-center gap-3">
              <Avatar src={t.user?.profile_picture_base64} name={t.user?.name} size={44} />
              <div>
                <div className="font-display font-bold">{t.user?.name || "Anonim"}</div>
                <div className="flex gap-0.5 mt-0.5">
                  {[1,2,3,4,5].map((n) => <Star key={n} weight={n <= t.rating ? "fill" : "regular"} size={14} className={n <= t.rating ? "text-[#FFD60A]" : "text-gray-400"} />)}
                </div>
              </div>
              <span className={`ml-auto brutal-sm px-2 py-1 text-xs font-mono uppercase ${t.status === "approved" ? "bg-[#34C759] text-white" : t.status === "rejected" ? "bg-[#FF3B30] text-white" : "bg-[#FFD60A]"}`}>{t.status}</span>
            </div>
            <p className="mt-3 text-sm">{t.comment}</p>
            <div className="mt-4 flex gap-2 flex-wrap">
              {t.status !== "approved" && (
                <button onClick={() => setStatus(t, "approved")} className="brutal-btn brutal-btn-green text-sm" data-testid={`approve-${t.id}`}>
                  <CheckCircle weight="bold" /> Setujui
                </button>
              )}
              {t.status !== "rejected" && (
                <button onClick={() => setStatus(t, "rejected")} className="brutal-btn brutal-btn-white text-sm" data-testid={`reject-${t.id}`}>
                  <X weight="bold" /> Tolak
                </button>
              )}
              <button onClick={() => del(t)} className="brutal-btn brutal-btn-red text-sm" data-testid={`delete-${t.id}`}>
                <Trash weight="bold" /> Hapus
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
