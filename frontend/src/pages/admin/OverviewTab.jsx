import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Broom } from "@phosphor-icons/react";
import { rupiah } from "@/lib/api";
import { Note } from "./shared";

export default function OverviewTab() {
  const [ana, setAna] = useState(null);
  const [cleaning, setCleaning] = useState(false);
  useEffect(() => { api.get("/admin/analytics").then((r) => setAna(r.data)).catch(() => {}); }, []);
  const totals = ana?.totals || {};

  const cleanup = async () => {
    const prefix = window.prompt("Hapus semua user yang namanya diawali (case-insensitive):", "Iter");
    if (!prefix) return;
    if (!window.confirm(`Yakin hapus semua user dengan nama diawali "${prefix}"? Termasuk subscriptions, payments & referral data mereka.`)) return;
    setCleaning(true);
    try {
      const { data } = await api.post(`/admin/cleanup-test-users?prefix=${encodeURIComponent(prefix)}`);
      toast.success(`${data.deleted_users} user + ${data.deleted_subscriptions} subs dihapus`);
    } catch (e) {
      toast.error("Cleanup gagal");
    } finally { setCleaning(false); }
  };

  return (
    <div className="space-y-6">
      <div className="brutal p-8 flex items-start justify-between flex-wrap gap-4">
        <div>
          <h2 className="font-display font-bold text-2xl">Selamat datang, Admin.</h2>
          <p className="mt-2 text-gray-700">Gunakan tab di atas untuk mengelola seluruh platform.</p>
        </div>
        <button onClick={cleanup} disabled={cleaning} className="brutal-btn brutal-btn-white text-sm" data-testid="admin-cleanup-btn">
          <Broom weight="bold" /> {cleaning ? "Membersihkan..." : "Cleanup test users"}
        </button>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <BigMetric label="Total pendapatan (paid)" value={rupiah(totals.total_revenue_paid || 0)} color="#34C759" />
        <BigMetric label="Pembayaran lunas" value={totals.paid_count || 0} color="#007AFF" />
        <BigMetric label="Rata-rata pembayaran" value={rupiah(Math.round(totals.avg_payment || 0))} color="#FFD60A" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="brutal p-6 lg:col-span-2" data-testid="analytics-monthly-chart">
          <div className="font-display font-bold text-xl mb-4">Pendapatan bulanan (12 bulan)</div>
          <div style={{ width: "100%", height: 280, minHeight: 280 }}>
            <ResponsiveContainer>
              <LineChart data={ana?.monthly || []} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#0A0A0A" strokeOpacity={0.1} />
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
          <div style={{ width: "100%", height: 280, minHeight: 280 }}>
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
        <Note title="Auto Scheduler (ACTIVE)" body="Background scheduler jalan setiap 1 jam, otomatis kirim reminder untuk tagihan H-N sesuai config. Trigger manual di tab Reminder." />
        <Note title="Activity Log" body="Semua aksi admin (create/delete/bulk/send reminder/scheduler run/export/referral) tercatat di tab Activity." />
        <Note title="Payment Gateway (Midtrans)" body="Snap invoice aktif — sandbox key terpasang. Webhook di /api/webhooks/midtrans; pasang di Midtrans Dashboard → Settings → Payment Notification URL." />
        <Note title="Reminder Email + WhatsApp" body="Isi SENDGRID_API_KEY dan TWILIO_ACCOUNT_SID/AUTH_TOKEN untuk notifikasi. Tanpa key, mode MOCKED." />
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
