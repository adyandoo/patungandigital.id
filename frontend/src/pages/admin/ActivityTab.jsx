import { useEffect, useState } from "react";
import api from "@/lib/api";

export default function ActivityTab() {
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
    if (a === "midtrans_webhook" || a === "xendit_webhook") return "bg-[#007AFF] text-white";
    if (a === "referral_reward_credited") return "bg-[#34C759] text-white";
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
