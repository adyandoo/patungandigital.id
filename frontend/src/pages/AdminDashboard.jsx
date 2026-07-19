import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Users, PaperPlaneTilt, Receipt, Storefront, Ticket, GearSix, ClockCounterClockwise } from "@phosphor-icons/react";
import OverviewTab from "./admin/OverviewTab";
import UsersTab from "./admin/UsersTab";
import ServicesTab from "./admin/ServicesTab";
import SubscriptionsTab from "./admin/SubscriptionsTab";
import PaymentsTab from "./admin/PaymentsTab";
import ReminderTab from "./admin/ReminderTab";
import ActivityTab from "./admin/ActivityTab";

const TABS = [
  { id: "overview", label: "Overview", icon: <GearSix weight="duotone" />, Comp: OverviewTab },
  { id: "users", label: "Users", icon: <Users weight="duotone" />, Comp: UsersTab },
  { id: "services", label: "Services", icon: <Storefront weight="duotone" />, Comp: ServicesTab },
  { id: "subscriptions", label: "Subscriptions", icon: <Ticket weight="duotone" />, Comp: SubscriptionsTab },
  { id: "payments", label: "Payments", icon: <Receipt weight="duotone" />, Comp: PaymentsTab },
  { id: "reminder", label: "Reminder", icon: <PaperPlaneTilt weight="duotone" />, Comp: ReminderTab },
  { id: "activity", label: "Activity", icon: <ClockCounterClockwise weight="duotone" />, Comp: ActivityTab },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState({});

  useEffect(() => { api.get("/admin/stats").then((r) => setStats(r.data)).catch(() => {}); }, [tab]);

  const Active = TABS.find((t) => t.id === tab)?.Comp || OverviewTab;

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
          <button
            key={t.id}
            data-testid={`admin-tab-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`px-4 py-3 font-display font-bold flex items-center gap-2 border-2 border-black border-b-0 -mb-[2px] whitespace-nowrap ${tab === t.id ? "bg-[#FFD60A]" : "bg-white"}`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      <div className="mt-8">
        <Active />
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
