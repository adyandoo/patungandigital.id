import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Trash, PaperPlaneTilt, Clock } from "@phosphor-icons/react";

export default function WaitlistTab() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/waitlist");
      setEntries(data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const del = async (id) => {
    if (!window.confirm("Hapus entry ini?")) return;
    await api.delete(`/admin/waitlist/${id}`);
    toast.success("Dihapus"); load();
  };

  const markContacted = async (id) => {
    await api.patch(`/admin/waitlist/${id}`, { status: "contacted" });
    toast.success("Ditandai contacted"); load();
  };

  const statusColor = (s) => ({ new: "bg-[#FFD60A]", contacted: "bg-[#007AFF] text-white", closed: "bg-gray-300" }[s] || "bg-white");

  return (
    <div>
      <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
        <div>
          <h2 className="font-display font-bold text-2xl">Waitlist ({entries.length})</h2>
          <p className="text-sm text-gray-700">Calon user yang antri karena slot layanan penuh.</p>
        </div>
        <button onClick={load} className="brutal-btn brutal-btn-white text-sm" data-testid="waitlist-refresh">Refresh</button>
      </div>
      {loading ? (
        <div className="brutal p-8 text-center text-gray-600">Memuat...</div>
      ) : entries.length === 0 ? (
        <div className="brutal p-8 text-center text-gray-600" data-testid="waitlist-empty">Belum ada entry waitlist.</div>
      ) : (
        <div className="brutal overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-black text-white">
              <tr>{["Waktu", "Email", "Nama", "WA", "Layanan", "Pesan", "Status", "Aksi"].map((h) => <th key={h} className="text-left px-4 py-3 font-mono uppercase text-xs">{h}</th>)}</tr>
            </thead>
            <tbody data-testid="waitlist-table">
              {entries.map((e) => (
                <tr key={e.id} className="border-t-2 border-black" data-testid={`waitlist-row-${e.id}`}>
                  <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">
                    <Clock size={12} className="inline mr-1" />
                    {new Date(e.created_at).toLocaleString("id-ID")}
                  </td>
                  <td className="px-4 py-3">
                    <a href={`mailto:${e.email}`} className="underline">{e.email}</a>
                  </td>
                  <td className="px-4 py-3">{e.name || "-"}</td>
                  <td className="px-4 py-3">
                    {e.whatsapp ? <a href={`https://wa.me/${e.whatsapp.replace(/[^0-9]/g, "")}`} target="_blank" rel="noreferrer" className="underline">{e.whatsapp}</a> : "-"}
                  </td>
                  <td className="px-4 py-3 font-semibold">{e.service_name || "-"}</td>
                  <td className="px-4 py-3 max-w-xs truncate text-gray-700">{e.message || "-"}</td>
                  <td className="px-4 py-3">
                    <span className={`pd-tag ${statusColor(e.status)}`}>{e.status || "new"}</span>
                  </td>
                  <td className="px-4 py-3 flex gap-1">
                    <button onClick={() => markContacted(e.id)} className="brutal-sm p-2 bg-[#007AFF] text-white text-xs" title="Tandai contacted" data-testid={`waitlist-contact-${e.id}`}>
                      <PaperPlaneTilt weight="bold" />
                    </button>
                    <button onClick={() => del(e.id)} className="brutal-sm p-2 bg-[#FF3B30] text-white text-xs" data-testid={`waitlist-delete-${e.id}`}>
                      <Trash weight="bold" />
                    </button>
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
