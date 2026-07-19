import { useEffect, useState } from "react";
import api, { rupiah, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Receipt, User, Lock, Ticket, UploadSimple, CheckCircle, ClockCounterClockwise, Gift, Copy, ShareNetwork, Trophy, Medal, Circle, CheckFat, Sparkle, UsersThree, Eye, EyeSlash, Key, QrCode, CurrencyCircleDollar, ArrowSquareOut, X as Xicon, Star, ChatCircleDots, ArrowClockwise, Warning, Camera, Trash, Megaphone, Info } from "@phosphor-icons/react";
import Avatar from "@/components/Avatar";

export default function UserDashboard() {
  const { user, setUser } = useAuth();
  const [tab, setTab] = useState("subs");
  const [subs, setSubs] = useState([]);
  const [payments, setPayments] = useState([]);
  const [onboarding, setOnboarding] = useState(null);
  const [announcements, setAnnouncements] = useState([]);
  const [showJoin, setShowJoin] = useState(false);

  const loadAll = async () => {
    try {
      const [s, p, o, a] = await Promise.all([
        api.get("/me/subscriptions"),
        api.get("/me/payments"),
        api.get("/me/onboarding"),
        api.get("/me/announcements"),
      ]);
      setSubs(s.data);
      setPayments(p.data);
      setOnboarding(o.data);
      setAnnouncements(a.data);
    } catch {}
  };

  const dismissAnn = async (id) => {
    try {
      await api.post(`/me/announcements/${id}/dismiss`);
      setAnnouncements(announcements.filter((a) => a.id !== id));
    } catch {}
  };

  useEffect(() => { loadAll(); }, []);
  // Deep link support: /dashboard?action=join opens the join modal immediately
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("action") === "join") setShowJoin(true);
    if (window.location.hash === "#join") setShowJoin(true);
  }, []);

  const openJoin = () => setShowJoin(true);

  return (
    <div className="px-6 md:px-12 py-10">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <Avatar src={user?.profile_picture_base64} name={user?.name} size={72} testId="header-avatar" />
          <div>
            <span className="pd-tag">Dashboard</span>
            <h1 className="font-display font-black text-4xl md:text-5xl mt-3">Halo, {user?.name}.</h1>
            <p className="text-gray-700 mt-1">Semua urusan patunganmu ada di sini.</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <button onClick={openJoin} className="brutal-btn brutal-btn-red" data-testid="header-join-btn">
            <Sparkle weight="fill" /> Ikut Patungan
          </button>
          <StatChip label="Langganan aktif" value={subs.filter((s) => s.status === "active").length} />
          <StatChip label="Tagihan" value={payments.filter((p) => p.status === "pending").length} />
          {user?.referral_credit > 0 && (
            <StatChip label="Kredit referral" value={rupiah(user.referral_credit)} />
          )}
        </div>
      </div>

      {/* Onboarding checklist */}
      {onboarding && onboarding.completed < onboarding.total && (
        <OnboardingCard data={onboarding} goToTab={setTab} openJoin={openJoin} />
      )}

      {/* Announcement banners */}
      {announcements.length > 0 && (
        <div className="mt-6 space-y-3" data-testid="announcement-banners">
          {announcements.map((a) => (
            <div key={a.id} className={`brutal p-5 flex items-start gap-4 flex-wrap ${a.severity === "critical" ? "bg-[#FF3B30] text-white" : a.severity === "warning" ? "bg-[#FFD60A]" : "bg-[#007AFF] text-white"}`} data-testid={`ann-banner-${a.id}`}>
              <Megaphone weight="fill" size={28} className="flex-shrink-0" />
              <div className="flex-1 min-w-[200px]">
                <div className="font-display font-black text-lg">{a.title}</div>
                <div className="text-sm mt-1 opacity-95 whitespace-pre-line">{a.body}</div>
              </div>
              <button onClick={() => dismissAnn(a.id)} className="brutal-sm bg-white text-black px-3 py-1 text-xs font-mono uppercase" data-testid={`ann-dismiss-${a.id}`}>
                Tutup
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="mt-8 flex gap-2 border-b-2 border-black overflow-x-auto">
        <TabBtn active={tab === "subs"} onClick={() => setTab("subs")} icon={<Ticket weight="duotone" />} label="Langganan" testid="tab-subs" />
        <TabBtn active={tab === "groups"} onClick={() => setTab("groups")} icon={<UsersThree weight="duotone" />} label="Grup & Akses" testid="tab-groups" />
        <TabBtn active={tab === "payments"} onClick={() => setTab("payments")} icon={<Receipt weight="duotone" />} label="Pembayaran" testid="tab-payments" />
        <TabBtn active={tab === "announcements"} onClick={() => setTab("announcements")} icon={<Megaphone weight="duotone" />} label="Pengumuman" testid="tab-announcements" />
        <TabBtn active={tab === "referral"} onClick={() => setTab("referral")} icon={<Gift weight="duotone" />} label="Referral" testid="tab-referral" />
        <TabBtn active={tab === "testimoni"} onClick={() => setTab("testimoni")} icon={<ChatCircleDots weight="duotone" />} label="Testimoni" testid="tab-testimoni" />
        <TabBtn active={tab === "profile"} onClick={() => setTab("profile")} icon={<User weight="duotone" />} label="Profil" testid="tab-profile" />
        <TabBtn active={tab === "password"} onClick={() => setTab("password")} icon={<Lock weight="duotone" />} label="Password" testid="tab-password" />
      </div>

      <div className="mt-8">
        {tab === "subs" && <SubsPanel subs={subs} reload={loadAll} openJoin={openJoin} />}
        {tab === "groups" && <GroupsPanel />}
        {tab === "payments" && <PaymentsPanel payments={payments} reload={loadAll} />}
        {tab === "announcements" && <AnnouncementsPanel />}
        {tab === "referral" && <ReferralPanel />}
        {tab === "testimoni" && <TestimoniPanel />}
        {tab === "profile" && <ProfilePanel user={user} setUser={setUser} />}
        {tab === "password" && <PasswordPanel />}
      </div>

      {showJoin && <JoinModal onClose={() => setShowJoin(false)} onJoined={() => { setShowJoin(false); setTab("payments"); loadAll(); }} />}
    </div>
  );
}

function OnboardingCard({ data, goToTab, openJoin }) {
  const nextAction = {
    profile: { tab: "profile", label: "Lengkapi profil sekarang" },
    first_payment: { tab: null, label: "Pilih & ikut patungan", action: openJoin },
    invite: { tab: "referral", label: "Ambil kode referral" },
    reward: { tab: "referral", label: "Ajak lebih banyak teman" },
  };
  const nextStep = data.steps.find((s) => !s.done);
  const next = nextStep ? nextAction[nextStep.key] : null;
  return (
    <div className="mt-6 brutal p-6 md:p-8 bg-gradient-to-br from-[#FFD60A]/40 to-white" data-testid="onboarding-card">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Sparkle weight="fill" size={22} />
            <div className="font-display font-bold text-xl">Mulai dari sini</div>
          </div>
          <div className="text-sm text-gray-700 mt-1">Selesaikan {data.total - data.completed} langkah lagi buat unlock full benefit patungan.</div>
        </div>
        <div className="text-right">
          <div className="font-display font-black text-4xl">{data.percent}%</div>
          <div className="text-xs font-mono text-gray-600">{data.completed}/{data.total} selesai</div>
        </div>
      </div>

      <div className="mt-4 h-3 border-2 border-black bg-white overflow-hidden">
        <div className="h-full bg-[#34C759]" style={{ width: `${data.percent}%` }}></div>
      </div>

      <div className="mt-6 grid md:grid-cols-5 gap-3" data-testid="onboarding-steps">
        {data.steps.map((s, idx) => (
          <div key={s.key} className={`brutal-sm p-3 flex items-start gap-2 ${s.done ? "bg-[#34C759]/25" : "bg-white"}`} data-testid={`onboarding-step-${s.key}`}>
            {s.done
              ? <CheckFat weight="fill" size={20} className="text-[#0A0A0A] shrink-0 mt-0.5" />
              : <Circle weight="regular" size={20} className="text-gray-400 shrink-0 mt-0.5" />}
            <div className="text-sm">
              <div className="font-mono text-[10px] text-gray-600">STEP {idx + 1}</div>
              <div className={`font-semibold ${s.done ? "line-through text-gray-600" : ""}`}>{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {next && (
        <button
          onClick={() => next.action ? next.action() : goToTab(next.tab)}
          className="brutal-btn brutal-btn-red mt-6"
          data-testid="onboarding-next-btn"
        >
          {next.label} →
        </button>
      )}
    </div>
  );
}

function StatChip({ label, value }) {
  return (
    <div className="brutal-sm bg-white px-4 py-2">
      <div className="font-mono text-xs uppercase text-gray-600">{label}</div>
      <div className="font-display font-black text-2xl">{value}</div>
    </div>
  );
}

function TabBtn({ active, onClick, icon, label, testid }) {
  return (
    <button data-testid={testid} onClick={onClick} className={`px-4 py-3 font-display font-bold flex items-center gap-2 border-2 border-black border-b-0 -mb-[2px] ${active ? "bg-[#FFD60A]" : "bg-white"}`}>
      {icon} {label}
    </button>
  );
}

function SubsPanel({ subs, reload, openJoin }) {
  const [warningDays, setWarningDays] = useState(7);
  const [renewingId, setRenewingId] = useState(null);
  useEffect(() => {
    api.get("/payment-config")
      .then((r) => setWarningDays(r.data.expiry_warning_days || 7))
      .catch(() => {});
  }, []);

  const renew = async (subId) => {
    if (!window.confirm("Buat tagihan perpanjangan sekarang?")) return;
    setRenewingId(subId);
    try {
      await api.post(`/me/subscriptions/${subId}/renew`, {});
      toast.success("Tagihan perpanjangan dibuat. Cek tab Pembayaran untuk pilih metode.");
      reload && reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setRenewingId(null); }
  };

  if (subs.length === 0) return (
    <div className="brutal p-8 md:p-10 bg-[#FFD60A]/40 text-center" data-testid="subs-empty">
      <Sparkle weight="fill" size={40} className="mx-auto" />
      <h3 className="mt-3 font-display font-black text-2xl">Belum ada langganan.</h3>
      <p className="mt-2 text-gray-700 max-w-md mx-auto">Mulai dengan pilih layanan (Netflix, Spotify, YouTube, dst) + durasi patungan yang kamu mau. Selesaikan pembayaran, admin akan assign kamu ke grup.</p>
      <button onClick={openJoin} className="brutal-btn brutal-btn-red mt-6" data-testid="subs-empty-join-btn">
        <Sparkle weight="fill" /> Pilih Layanan & Ikut Patungan
      </button>
    </div>
  );

  const now = Date.now();
  const expiring = subs
    .map((s) => {
      if (!s.end_date) return null;
      const t = new Date(s.end_date).getTime();
      const daysLeft = Math.floor((t - now) / 86400000);
      if (daysLeft < 0) return { ...s, daysLeft, expired: true };
      if (daysLeft <= warningDays) return { ...s, daysLeft, expired: false };
      return null;
    })
    .filter(Boolean);

  return (
    <div className="space-y-6" data-testid="subs-panel">
      {expiring.map((s) => (
        <div key={"warn-" + s.id} className={`brutal p-5 flex flex-wrap items-center gap-4 ${s.expired ? "bg-[#FF3B30] text-white" : "bg-[#FFD60A]"}`} data-testid={`expiry-banner-${s.id}`}>
          <Warning weight="fill" size={32} />
          <div className="flex-1 min-w-[220px]">
            <div className="font-display font-black text-xl">
              {s.expired
                ? `Langganan ${s.service?.name} sudah expired ${Math.abs(s.daysLeft)} hari lalu.`
                : `Langganan ${s.service?.name} berakhir ${s.daysLeft === 0 ? "hari ini" : `${s.daysLeft} hari lagi`}.`}
            </div>
            <div className="text-sm mt-1 opacity-80">Perpanjang sekarang biar layanannya tidak putus.</div>
          </div>
          <button
            disabled={renewingId === s.id}
            onClick={() => renew(s.id)}
            className={`brutal-btn ${s.expired ? "brutal-btn-white text-black" : "brutal-btn-red"}`}
            data-testid={`renew-btn-${s.id}`}
          >
            <ArrowClockwise weight="bold" /> {renewingId === s.id ? "Membuat tagihan..." : "Perpanjang sekarang"}
          </button>
        </div>
      ))}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="subs-grid">
        {subs.map((s) => (
          <div key={s.id} className="brutal p-6" data-testid={`sub-card-${s.id}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-display font-black text-2xl">{s.service?.name}</div>
                <div className="pd-tag mt-2">{s.role === "host" ? "Host" : "Regular"}</div>
              </div>
              <span className={`px-2 py-1 font-mono text-xs border-2 border-black ${s.status === "active" ? "bg-[#34C759] text-white" : "bg-gray-200"}`}>{s.status}</span>
            </div>
            <div className="mt-4 space-y-1 text-sm">
              <div><span className="font-mono text-gray-600">Mulai:</span> {formatDate(s.start_date)}</div>
              {s.end_date && <div><span className="font-mono text-gray-600">Sampai:</span> {formatDate(s.end_date)}</div>}
              <div className="mt-2 font-display font-black text-xl">{rupiah(s.price)}<span className="text-sm font-normal">/periode</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PaymentsPanel({ payments, reload }) {
  const [uploadingId, setUploadingId] = useState(null);
  const [choosingId, setChoosingId] = useState(null);
  const [config, setConfig] = useState(null);
  const [qrisOpenFor, setQrisOpenFor] = useState(null);

  useEffect(() => { api.get("/payment-config").then((r) => setConfig(r.data)).catch(() => {}); }, []);

  const upload = async (paymentId, file) => {
    setUploadingId(paymentId);
    try {
      const b64 = await toBase64(file);
      await api.post(`/me/payments/${paymentId}/receipt`, {
        payment_id: paymentId,
        file_base64: b64,
        file_name: file.name,
      });
      toast.success("Bukti transfer diunggah — status otomatis PAID. Admin akan verifikasi.");
      reload();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setUploadingId(null);
    }
  };

  const chooseMethod = async (paymentId, method) => {
    setChoosingId(paymentId);
    try {
      const { data } = await api.post(`/me/payments/${paymentId}/choose-method`, { method });
      toast.success(method === "midtrans" ? "Invoice Midtrans dibuat." : "Metode QRIS dipilih.");
      reload();
      if (method === "qris") setQrisOpenFor(data.id);
      else if (data.midtrans_redirect_url) window.open(data.midtrans_redirect_url, "_blank");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setChoosingId(null);
    }
  };

  if (payments.length === 0) return <EmptyState msg="Belum ada tagihan." />;
  return (
    <div className="space-y-4" data-testid="payments-list">
      {payments.map((p) => (
        <div key={p.id} className="brutal p-6 md:p-8" data-testid={`payment-card-${p.id}`}>
          <div className="grid md:grid-cols-4 gap-4">
            <div>
              <div className="font-mono text-xs uppercase text-gray-600">Layanan</div>
              <div className="font-display font-bold text-xl">{p.service_name}</div>
              <div className="text-sm text-gray-600 mt-1">{p.period_label}</div>
            </div>
            <div>
              <div className="font-mono text-xs uppercase text-gray-600">Jumlah</div>
              <div className="font-display font-black text-2xl">{rupiah(p.amount)}</div>
              {p.midtrans_fee > 0 && (
                <div className="text-xs text-gray-600">Termasuk biaya Midtrans +{p.midtrans_fee_percent || 5}% = {rupiah(p.midtrans_fee)}</div>
              )}
              {p.due_date && <div className="text-sm text-gray-600 mt-1">Jatuh tempo {formatDate(p.due_date)}</div>}
            </div>
            <div>
              <div className="font-mono text-xs uppercase text-gray-600">Status</div>
              <StatusPill status={p.status} />
              {p.payment_method && (
                <div className="mt-2 text-xs font-mono uppercase">
                  Metode: <b>{p.payment_method === "midtrans" ? "Midtrans" : "QRIS Manual"}</b>
                </div>
              )}
              {p.receipt && (
                <div className="text-xs text-gray-600 mt-2">
                  <ClockCounterClockwise size={14} className="inline" /> Bukti diunggah {formatDateTime(p.receipt.uploaded_at)}
                </div>
              )}
            </div>
            <div className="flex flex-col items-start gap-2">
              {p.status === "paid" ? (
                <div className="brutal-sm bg-[#34C759] text-white px-4 py-2 font-mono text-sm">
                  <CheckCircle weight="fill" className="inline mr-1" /> Lunas
                </div>
              ) : !p.payment_method ? (
                // Method chooser
                <div className="w-full space-y-2" data-testid={`method-chooser-${p.id}`}>
                  <button disabled={choosingId === p.id} onClick={() => chooseMethod(p.id, "qris")}
                          className="brutal-btn brutal-btn-yellow text-sm w-full justify-center relative"
                          data-testid={`choose-qris-${p.id}`}>
                    <QrCode weight="bold" /> QRIS Manual — Rp 0 fee
                    <span className="absolute -top-2 -right-2 pd-tag bg-[#34C759] text-white text-[9px]">DIREKOMENDASIKAN</span>
                  </button>
                  <button disabled={choosingId === p.id} onClick={() => chooseMethod(p.id, "midtrans")}
                          className="brutal-btn brutal-btn-blue text-sm w-full justify-center"
                          data-testid={`choose-midtrans-${p.id}`}>
                    <CurrencyCircleDollar weight="bold" /> Midtrans (Otomatis) +{config?.midtrans_fee_percent || 5}%
                  </button>
                </div>
              ) : p.payment_method === "midtrans" ? (
                <>
                  {p.midtrans_redirect_url && (
                    <a href={p.midtrans_redirect_url} target="_blank" rel="noreferrer" className="brutal-btn brutal-btn-blue text-sm" data-testid={`pay-midtrans-${p.id}`}>
                      Lanjut bayar via Midtrans <ArrowSquareOut weight="bold" />
                    </a>
                  )}
                  <button onClick={() => resetMethod(p.id)} className="brutal-sm bg-white px-3 py-1 text-xs" data-testid={`reset-method-${p.id}`}>
                    Ganti metode
                  </button>
                </>
              ) : (
                // QRIS chosen
                <>
                  <button onClick={() => setQrisOpenFor(p.id)} className="brutal-btn brutal-btn-yellow text-sm" data-testid={`view-qris-${p.id}`}>
                    <QrCode weight="bold" /> Lihat QRIS
                  </button>
                  <label className="brutal-btn brutal-btn-red text-sm cursor-pointer" data-testid={`upload-receipt-${p.id}`}>
                    <UploadSimple weight="bold" />
                    {uploadingId === p.id ? "Mengunggah..." : p.receipt ? "Ganti bukti" : "Upload bukti"}
                    <input type="file" accept="image/*,application/pdf" className="hidden" onChange={(e) => e.target.files[0] && upload(p.id, e.target.files[0])} />
                  </label>
                  <button onClick={() => resetMethod(p.id)} className="brutal-sm bg-white px-3 py-1 text-xs" data-testid={`reset-method-${p.id}`}>
                    Ganti metode
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
      {qrisOpenFor && config && (
        <QrisModal config={config} amount={payments.find((p) => p.id === qrisOpenFor)?.amount || 0} onClose={() => setQrisOpenFor(null)} />
      )}
    </div>
  );

  async function resetMethod(id) {
    // Just re-open chooser — call chooseMethod again lets user pick differently
    if (!window.confirm("Batalkan metode sebelumnya dan pilih ulang?")) return;
    try {
      // Set to qris as neutral state? Better: server endpoint to reset. For simplicity, ask user to re-pick.
      // We'll just null out via choose-method call using a special server call — but current server doesn't support null.
      // Simpler client-side: force chooser by calling choose qris (0 fee) and letting them re-decide upload.
      toast.info("Silakan pilih metode baru.");
      // We could add a proper reset endpoint later; for now toggle to opposite quickly.
      const cur = payments.find((x) => x.id === id);
      const target = cur?.payment_method === "midtrans" ? "qris" : "midtrans";
      await chooseMethod(id, target);
    } catch {}
  }
}

function QrisModal({ config, amount, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="brutal-lg bg-white max-w-md w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="qris-modal">
        <div className="border-b-2 border-black p-4 bg-[#FFD60A] flex items-center justify-between">
          <div className="font-display font-black text-xl">Scan QRIS</div>
          <button onClick={onClose}><Xicon weight="bold" size={24} /></button>
        </div>
        <div className="p-6 space-y-4 text-center">
          <div className="font-mono text-xs uppercase text-gray-600">Jumlah bayar</div>
          <div className="font-display font-black text-4xl">{rupiah(amount)}</div>
          {config.qris_image_base64 ? (
            <img src={config.qris_image_base64} alt="QRIS" className="mx-auto max-h-80 border-2 border-black" data-testid="qris-image" />
          ) : (
            <div className="brutal-sm bg-white p-8">
              <QrCode weight="duotone" size={80} className="mx-auto text-gray-400" />
              <div className="mt-2 text-sm text-gray-600">QRIS belum tersedia. Admin akan menghubungimu.</div>
            </div>
          )}
          {config.qris_notes && <div className="text-sm text-gray-700 whitespace-pre-line">{config.qris_notes}</div>}
          {config.manual_bank_info && (
            <div className="brutal-sm bg-white p-3 text-sm text-left">
              <div className="font-mono text-xs uppercase text-gray-600 mb-1">Atau transfer manual</div>
              <div className="whitespace-pre-line">{config.manual_bank_info}</div>
            </div>
          )}
          <div className="brutal-sm bg-[#34C759]/20 p-3 text-sm text-left">
            Setelah transfer, tutup dialog ini lalu klik <b>Upload bukti</b> pada tagihan. Status otomatis jadi <b>PAID</b>.
          </div>
          <button onClick={onClose} className="brutal-btn brutal-btn-red">Tutup</button>
        </div>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = { pending: "bg-[#FFD60A]", review: "bg-[#007AFF] text-white", paid: "bg-[#34C759] text-white", overdue: "bg-[#FF3B30] text-white" };
  return <span className={`px-2 py-1 font-mono text-xs border-2 border-black inline-block ${map[status] || "bg-white"}`}>{status}</span>;
}

function ProfilePanel({ user, setUser }) {
  const [form, setForm] = useState({
    name: user?.name || "",
    username: user?.username || "",
    whatsapp: user?.whatsapp || "",
    gender: user?.gender || "",
  });

  const save = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.patch("/auth/profile", form);
      setUser(data);
      toast.success("Profil tersimpan.");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <ProfilePicturePicker user={user} setUser={setUser} />
      <form onSubmit={save} className="brutal p-6 md:p-10" data-testid="profile-form">
        <h3 className="font-display font-bold text-2xl">Informasi profil</h3>
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Nama"><input data-testid="prof-name" className="brutal-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Username"><input data-testid="prof-username" className="brutal-input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></Field>
          <Field label="Email"><input className="brutal-input bg-gray-100" value={user?.email} disabled /></Field>
          <Field label="WhatsApp"><input data-testid="prof-whatsapp" className="brutal-input" value={form.whatsapp} onChange={(e) => setForm({ ...form, whatsapp: e.target.value })} /></Field>
          <Field label="Gender">
            <select data-testid="prof-gender" className="brutal-input" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
              <option value="">-</option><option value="L">Laki-laki</option><option value="P">Perempuan</option>
            </select>
          </Field>
        </div>
        {user?.extra && Object.keys(user.extra).length > 0 && (
          <div className="mt-6">
            <div className="font-mono text-xs uppercase text-gray-600 mb-2">Info tambahan (dari admin)</div>
            <div className="brutal-sm bg-[#FFD60A]/40 p-4 space-y-1">
              {Object.entries(user.extra).map(([k, v]) => (
                <div key={k} className="text-sm"><span className="font-mono">{k}:</span> {String(v)}</div>
              ))}
            </div>
          </div>
        )}
        <button type="submit" className="brutal-btn brutal-btn-red mt-8" data-testid="prof-save">
          <CheckCircle weight="bold" /> Simpan
        </button>
      </form>
    </div>
  );
}

function ProfilePicturePicker({ user, setUser }) {
  const [busy, setBusy] = useState(false);
  const pick = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const b64 = await resizeImageTo512(file);
      const { data } = await api.put("/auth/profile-picture", { profile_picture_base64: b64 });
      setUser(data);
      toast.success("Foto profil diperbarui.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Gagal upload"); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm("Hapus foto profil?")) return;
    try {
      const { data } = await api.put("/auth/profile-picture", { profile_picture_base64: null });
      setUser(data);
      toast.success("Foto profil dihapus.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="brutal p-6 md:p-8 flex items-center gap-6 flex-wrap" data-testid="profile-picture-card">
      <Avatar src={user?.profile_picture_base64} name={user?.name} size={96} testId="profile-avatar-preview" />
      <div className="flex-1 min-w-[200px]">
        <h3 className="font-display font-bold text-xl">Foto profil</h3>
        <p className="text-sm text-gray-700 mt-1">Format JPG/PNG, otomatis diperkecil ke 512×512. Kalau kosong, kami tampilkan avatar warna dari inisial namamu.</p>
      </div>
      <div className="flex gap-2">
        <label className="brutal-btn brutal-btn-blue cursor-pointer" data-testid="profile-pic-upload">
          <Camera weight="bold" /> {busy ? "Mengunggah..." : (user?.profile_picture_base64 ? "Ganti" : "Upload")}
          <input type="file" accept="image/*" className="hidden" onChange={(e) => pick(e.target.files[0])} />
        </label>
        {user?.profile_picture_base64 && (
          <button onClick={remove} className="brutal-btn brutal-btn-white" data-testid="profile-pic-remove"><Trash weight="bold" /></button>
        )}
      </div>
    </div>
  );
}

async function resizeImageTo512(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const size = 512;
      const scale = Math.min(size / img.width, size / img.height, 1);
      const w = Math.round(img.width * scale);
      const h = Math.round(img.height * scale);
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = reject;
    const r = new FileReader();
    r.onload = () => { img.src = r.result; };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function TestimoniPanel() {
  const [items, setItems] = useState([]);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/me/testimonials").then((r) => setItems(r.data)).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if ((comment || "").trim().length < 10) return toast.error("Komentar minimal 10 karakter.");
    setBusy(true);
    try {
      if (editingId) {
        await api.patch(`/me/testimonials/${editingId}`, { rating, comment });
        toast.success("Testimoni diperbarui. Menunggu review admin.");
      } else {
        await api.post("/me/testimonials", { rating, comment });
        toast.success("Testimoni dikirim! Menunggu review admin.");
      }
      setEditingId(null); setRating(5); setComment(""); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const startEdit = (t) => {
    if (t.status === "approved") return toast.info("Testimoni sudah disetujui admin dan tidak bisa diedit. Hapus dulu untuk buat baru.");
    setEditingId(t.id); setRating(t.rating); setComment(t.comment);
  };
  const del = async (t) => {
    if (!window.confirm("Hapus testimoni ini?")) return;
    try { await api.delete(`/me/testimonials/${t.id}`); toast.success("Testimoni dihapus."); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="grid md:grid-cols-2 gap-8" data-testid="testimoni-panel">
      <form onSubmit={submit} className="brutal p-6 md:p-8 space-y-4" data-testid="testimoni-form">
        <h3 className="font-display font-bold text-2xl">
          {editingId ? "Edit testimoni" : "Tulis testimoni"}
        </h3>
        <p className="text-sm text-gray-700">Cerita positif kamu akan membantu calon user lain untuk percaya patungandigital.id 💛</p>
        <Field label="Rating">
          <div className="flex gap-1" data-testid="rating-stars">
            {[1,2,3,4,5].map((n) => (
              <button type="button" key={n} onClick={() => setRating(n)} data-testid={`rating-${n}`}>
                <Star weight={n <= rating ? "fill" : "regular"} size={32} className={n <= rating ? "text-[#FFD60A]" : "text-gray-400"} />
              </button>
            ))}
          </div>
        </Field>
        <Field label={`Komentar (${comment.length}/500)`}>
          <textarea rows={5} className="brutal-input" value={comment} onChange={(e) => setComment(e.target.value.slice(0, 500))} placeholder="Cerita pengalamanmu pakai patungandigital.id..." data-testid="testimoni-comment" />
        </Field>
        <div className="flex gap-2">
          <button disabled={busy} type="submit" className="brutal-btn brutal-btn-red" data-testid="testimoni-submit">
            <CheckCircle weight="bold" /> {editingId ? "Simpan perubahan" : "Kirim testimoni"}
          </button>
          {editingId && (
            <button type="button" onClick={() => { setEditingId(null); setRating(5); setComment(""); }} className="brutal-btn brutal-btn-white" data-testid="testimoni-cancel">Batal</button>
          )}
        </div>
      </form>

      <div className="space-y-4" data-testid="testimoni-list">
        <h3 className="font-display font-bold text-2xl">Testimoni kamu</h3>
        {items.length === 0 && <EmptyState msg="Belum ada testimoni." />}
        {items.map((t) => (
          <div key={t.id} className="brutal p-5" data-testid={`testimoni-${t.id}`}>
            <div className="flex items-center justify-between">
              <div className="flex gap-0.5" aria-label={`${t.rating} bintang`}>
                {[1,2,3,4,5].map((n) => <Star key={n} weight={n <= t.rating ? "fill" : "regular"} size={16} className={n <= t.rating ? "text-[#FFD60A]" : "text-gray-400"} />)}
              </div>
              <StatusPillTestimoni status={t.status} />
            </div>
            <p className="mt-3 text-sm">{t.comment}</p>
            <div className="mt-3 flex gap-2">
              <button onClick={() => startEdit(t)} className="brutal-sm px-3 py-1 text-xs bg-[#007AFF] text-white" data-testid={`testimoni-edit-${t.id}`}>Edit</button>
              <button onClick={() => del(t)} className="brutal-sm px-3 py-1 text-xs bg-[#FF3B30] text-white" data-testid={`testimoni-delete-${t.id}`}>Hapus</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusPillTestimoni({ status }) {
  const map = {
    pending: { text: "Menunggu review", bg: "bg-[#FFD60A]", fg: "text-black" },
    approved: { text: "Tayang di homepage", bg: "bg-[#34C759]", fg: "text-white" },
    rejected: { text: "Ditolak", bg: "bg-[#FF3B30]", fg: "text-white" },
  };
  const m = map[status] || map.pending;
  return <span className={`brutal-sm px-2 py-1 text-xs font-mono uppercase ${m.bg} ${m.fg}`}>{m.text}</span>;
}

function AnnouncementsPanel() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    api.get("/me/announcements?only_active=false").then((r) => setItems(r.data)).catch(() => setItems([]));
  }, []);
  if (items.length === 0) return <EmptyState msg="Belum ada pengumuman." />;
  return (
    <div className="space-y-3 max-w-3xl" data-testid="announcements-panel">
      {items.map((a) => {
        const sev = a.severity === "critical" ? "bg-[#FF3B30] text-white" : a.severity === "warning" ? "bg-[#FFD60A]" : "bg-[#007AFF] text-white";
        return (
          <div key={a.id} className={`brutal p-5 ${sev}`} data-testid={`ann-archive-${a.id}`}>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                <Megaphone weight="fill" size={20} />
                <span className="pd-tag bg-white text-black">{a.severity}</span>
                {a.dismissed && <span className="pd-tag bg-white/40 text-white">Sudah dibaca</span>}
              </div>
              <span className="text-xs font-mono opacity-80">{a.created_at ? new Date(a.created_at).toLocaleString("id-ID") : ""}</span>
            </div>
            <div className="font-display font-black text-lg mt-2">{a.title}</div>
            <div className="text-sm mt-1 opacity-95 whitespace-pre-line">{a.body}</div>
          </div>
        );
      })}
    </div>
  );
}

function PasswordPanel() {
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/auth/change-password", form);
      toast.success("Password diubah.");
      setForm({ current_password: "", new_password: "" });
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };
  return (
    <form onSubmit={submit} className="brutal p-6 md:p-10 max-w-md" data-testid="password-form">
      <h3 className="font-display font-bold text-2xl">Ubah password</h3>
      <div className="mt-6 space-y-4">
        <Field label="Password saat ini">
          <input data-testid="pw-current" type="password" required className="brutal-input" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} />
        </Field>
        <Field label="Password baru (min. 6)">
          <input data-testid="pw-new" type="password" minLength={6} required className="brutal-input" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} />
        </Field>
      </div>
      <button type="submit" className="brutal-btn brutal-btn-red mt-8" data-testid="pw-submit">Ubah password</button>
    </form>
  );
}

function ReferralPanel() {
  const [stats, setStats] = useState(null);
  const [board, setBoard] = useState(null);
  useEffect(() => {
    api.get("/me/referral-stats").then((r) => setStats(r.data));
    api.get("/leaderboard").then((r) => setBoard(r.data));
  }, []);
  if (!stats) return <div className="brutal p-8">Memuat...</div>;

  const shareText = `Halo! Yuk patungan langganan premium bareng di patungandigital.id. Pakai kode referralku *${stats.referral_code}* biar kita berdua dapat diskon Rp ${stats.reward_per_referral.toLocaleString("id-ID")}!`;
  const shareLink = `${window.location.origin}/register?ref=${stats.referral_code}`;

  const copy = (text, label = "Disalin!") => {
    navigator.clipboard.writeText(text).then(() => toast.success(label)).catch(() => toast.error("Gagal menyalin"));
  };
  const shareWA = () => {
    const url = `https://wa.me/?text=${encodeURIComponent(shareText + " " + shareLink)}`;
    window.open(url, "_blank");
  };

  const nextTier = stats.next_tier;
  const progressPct = nextTier ? Math.min(100, Math.round((stats.successful_count / nextTier.referrals) * 100)) : 100;

  return (
    <div className="space-y-6" data-testid="referral-panel">
      <div className="grid md:grid-cols-3 gap-6">
        <div className="brutal p-8 md:col-span-2 bg-[#FFD60A]/30">
          <div className="flex items-center gap-3">
            <Gift weight="fill" size={32} />
            <h3 className="font-display font-bold text-2xl">Kode referral kamu</h3>
          </div>
          <p className="mt-2 text-gray-800">Ajak teman patungan. Setiap teman yang daftar & bayar pertama, kalian <b>berdua dapat diskon Rp {stats.reward_per_referral.toLocaleString("id-ID")}</b>. Ada bonus tier untuk yang paling rajin.</p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <div className="brutal-sm bg-white px-6 py-4 font-mono font-black text-3xl tracking-widest" data-testid="referral-code">{stats.referral_code}</div>
            <button onClick={() => copy(stats.referral_code, "Kode disalin!")} className="brutal-btn brutal-btn-white" data-testid="referral-copy-code">
              <Copy weight="bold" /> Salin kode
            </button>
            <button onClick={() => copy(shareLink, "Link disalin!")} className="brutal-btn brutal-btn-white" data-testid="referral-copy-link">
              <Copy weight="bold" /> Salin link
            </button>
            <button onClick={shareWA} className="brutal-btn brutal-btn-green" data-testid="referral-share-wa">
              <ShareNetwork weight="bold" /> Share ke WhatsApp
            </button>
          </div>
          {stats.referred_by && (
            <div className="mt-6 brutal-sm bg-white p-3 text-sm">Kamu diundang oleh <b>{stats.referred_by.name}</b>. Terima kasih! 🎉</div>
          )}
        </div>
        <div className="grid gap-4">
          <div className="brutal p-5">
            <div className="font-mono text-xs uppercase text-gray-600">Kredit tersedia</div>
            <div className="font-display font-black text-3xl mt-1">{rupiah(stats.referral_credit)}</div>
          </div>
          <div className="brutal p-5 bg-[#34C759]/20">
            <div className="font-mono text-xs uppercase text-gray-600">Bulan gratis</div>
            <div className="font-display font-black text-3xl mt-1">{stats.free_months_credit || 0} bulan</div>
            <div className="text-xs text-gray-600 mt-1">Otomatis dipakai untuk tagihan berikutnya.</div>
          </div>
        </div>
      </div>

      {/* Tier progress */}
      <div className="brutal p-6" data-testid="tier-progress">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="font-display font-bold text-xl">Progress tier reward</div>
            <div className="text-sm text-gray-600">Berhasil ajak: <b>{stats.successful_count}</b> teman (dari {stats.invited_count} yang daftar)</div>
          </div>
          {nextTier ? (
            <div className="text-sm font-mono">Menuju <b>Tier {nextTier.tier}</b>: {stats.successful_count}/{nextTier.referrals} — <b>+{nextTier.free_months} bulan gratis</b></div>
          ) : (
            <div className="pd-tag bg-[#34C759] text-white">Semua tier terbuka! 🏆</div>
          )}
        </div>
        {nextTier && (
          <div className="mt-4 h-4 border-2 border-black bg-white relative overflow-hidden">
            <div className="h-full bg-[#FFD60A]" style={{ width: `${progressPct}%` }}></div>
          </div>
        )}
        <div className="grid md:grid-cols-3 gap-3 mt-6">
          {stats.tiers.map((t) => {
            const unlocked = (stats.tiers_granted || []).includes(t.tier);
            return (
              <div key={t.tier} className={`brutal-sm p-4 ${unlocked ? "bg-[#34C759]/20" : "bg-white"}`}>
                <div className="flex items-center gap-2">
                  <Medal weight={unlocked ? "fill" : "duotone"} size={22} />
                  <div className="font-display font-bold">Tier {t.tier}</div>
                  {unlocked && <span className="pd-tag bg-[#34C759] text-white text-[10px]">terbuka</span>}
                </div>
                <div className="text-sm mt-2">{t.referrals} teman berhasil = <b>{t.free_months} bulan gratis</b></div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Leaderboard */}
      {board && board.monthly.length > 0 && (
        <div className="brutal p-6" data-testid="referral-leaderboard">
          <div className="flex items-center gap-2 mb-4">
            <Trophy weight="fill" size={26} />
            <div>
              <div className="font-display font-bold text-xl">Leaderboard bulan ini</div>
              <div className="text-sm text-gray-600 font-mono">{board.month_label}</div>
            </div>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <LeaderboardList title="Bulan ini" rows={board.monthly} />
            <LeaderboardList title="All time" rows={board.all_time} />
          </div>
        </div>
      )}
    </div>
  );
}

function LeaderboardList({ title, rows }) {
  return (
    <div className="brutal-sm bg-white p-4">
      <div className="font-display font-bold mb-3">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-gray-600">Belum ada.</div>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.user_id + r.rank} className="flex items-center justify-between border-b border-black/10 pb-2">
              <div className="flex items-center gap-3">
                <span className={`w-8 h-8 flex items-center justify-center font-mono font-black text-sm ${r.rank === 1 ? "bg-[#FFD60A] border-2 border-black" : r.rank === 2 ? "bg-white border-2 border-black" : r.rank === 3 ? "bg-[#FF3B30] text-white border-2 border-black" : "text-gray-600"}`}>
                  {r.rank <= 3 ? <Medal weight="fill" /> : `#${r.rank}`}
                </span>
                <div>
                  <div className="font-semibold text-sm">{r.name}</div>
                  <div className="text-xs text-gray-600 font-mono">{r.count} teman</div>
                </div>
              </div>
              <div className="text-right font-display font-black text-sm">{rupiah(r.total_earned)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="font-mono text-xs uppercase mb-2">{label}</div>
      {children}
    </label>
  );
}

function EmptyState({ msg }) {
  return <div className="brutal p-10 text-center text-gray-700">{msg}</div>;
}

function formatDate(d) {
  if (!d) return "-";
  return new Date(d).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
}
function formatDateTime(d) {
  if (!d) return "-";
  return new Date(d).toLocaleString("id-ID", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function toBase64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}


function GroupsPanel() {
  const [groups, setGroups] = useState(null);
  useEffect(() => { api.get("/me/groups").then((r) => setGroups(r.data)).catch(() => setGroups([])); }, []);
  if (groups === null) return <div className="brutal p-8">Memuat...</div>;
  if (groups.length === 0) return <div className="brutal p-10 text-center text-gray-700" data-testid="groups-empty">Belum ada grup. Setelah admin menempatkanmu ke grup layanan, info akan muncul di sini.</div>;
  return (
    <div className="grid md:grid-cols-2 gap-6" data-testid="my-groups">
      {groups.map((g, i) => <GroupCard key={g.group.id + i} data={g} />)}
    </div>
  );
}

function GroupCard({ data }) {
  const [showPw, setShowPw] = useState(false);
  const { group, service, role, members, credential } = data;
  const copy = (t, label = "Disalin!") => navigator.clipboard.writeText(t).then(() => toast.success(label));
  return (
    <div className="brutal overflow-hidden" data-testid={`group-item-${group.id}`}>
      <div className="p-4 border-b-2 border-black" style={{ background: service?.color || "#0A0A0A", color: "#fff" }}>
        <div className="text-xs font-mono uppercase opacity-80">{service?.name}</div>
        <div className="font-display font-black text-2xl">{group.name}</div>
      </div>
      <div className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <UsersThree weight="duotone" size={20} />
          <span className="pd-tag">{role}</span>
          <span className="text-sm text-gray-600 font-mono">{members.length}/{group.host_slots + group.regular_slots} anggota</span>
        </div>
        <div>
          <div className="font-mono text-xs uppercase text-gray-600 mb-2">Anggota grup</div>
          <ul className="space-y-1 text-sm">
            {members.map((m, idx) => (
              <li key={idx} className={`flex items-center justify-between border-b border-black/10 pb-1 ${m.is_me ? "font-bold" : ""}`}>
                <span>{m.name} {m.is_me && <span className="text-[10px] font-mono text-gray-600">(kamu)</span>}</span>
                <span className={`pd-tag text-[10px] ${m.role === "host" ? "bg-[#FFD60A]" : "bg-white"}`}>{m.role}</span>
              </li>
            ))}
          </ul>
        </div>
        {credential ? (
          <div className="brutal-sm bg-[#FFD60A]/40 p-4" data-testid={`group-credential-${group.id}`}>
            <div className="flex items-center gap-2">
              <Key weight="fill" size={18} />
              <div className="font-display font-bold">Akses login</div>
            </div>
            <div className="mt-3 space-y-2">
              <div>
                <div className="font-mono text-[10px] uppercase text-gray-600">Email</div>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm break-all">{credential.email}</span>
                  <button onClick={() => copy(credential.email, "Email disalin!")} className="brutal-sm p-1 bg-white" data-testid={`copy-email-${group.id}`}><Copy weight="bold" size={14} /></button>
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase text-gray-600">Password</div>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm break-all">{showPw ? credential.password : "••••••••••"}</span>
                  <div className="flex gap-1">
                    <button onClick={() => setShowPw((s) => !s)} className="brutal-sm p-1 bg-white" data-testid={`toggle-pw-${group.id}`}>
                      {showPw ? <EyeSlash weight="bold" size={14} /> : <Eye weight="bold" size={14} />}
                    </button>
                    <button onClick={() => copy(credential.password, "Password disalin!")} className="brutal-sm p-1 bg-white" data-testid={`copy-pw-${group.id}`}><Copy weight="bold" size={14} /></button>
                  </div>
                </div>
              </div>
              {credential.notes && (
                <div className="text-xs text-gray-800 mt-2 border-t border-black/20 pt-2">{credential.notes}</div>
              )}
            </div>
          </div>
        ) : (
          <div className="brutal-sm bg-white p-3 text-sm text-gray-600">
            Belum ada akses login dari admin untuk grup ini.
          </div>
        )}
      </div>
    </div>
  );
}


// ---- Join / Ikut Patungan Modal ---- //
function JoinModal({ onClose, onJoined }) {
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pickedService, setPickedService] = useState(null);
  const [duration, setDuration] = useState(1);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/services")
      .then((r) => { setServices(r.data.filter((s) => s.active !== false)); setLoading(false); })
      .catch(() => { setLoading(false); });
  }, []);

  useEffect(() => {
    if (pickedService) setDuration(pickedService.min_duration_months || 1);
  }, [pickedService]);

  const durations = [1, 3, 6, 12];
  const price = pickedService ? (pickedService.price_regular || 0) * duration : 0;

  const submit = async () => {
    if (!pickedService) return toast.error("Pilih layanan dulu.");
    if (duration < (pickedService.min_duration_months || 1)) {
      return toast.error(`Durasi minimum untuk ${pickedService.name} adalah ${pickedService.min_duration_months} bulan.`);
    }
    setBusy(true);
    try {
      await api.post("/me/subscriptions/join", { service_id: pickedService.id, duration_months: duration });
      toast.success(`Berhasil daftar ${pickedService.name}. Selesaikan pembayaran di tab Pembayaran.`);
      onJoined && onJoined();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose} data-testid="join-modal">
      <div className="brutal bg-white max-w-3xl w-full max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="border-b-4 border-black bg-[#FFD60A] p-5 flex items-center justify-between">
          <div>
            <div className="pd-tag bg-black text-white">Ikut Patungan</div>
            <h2 className="font-display font-black text-2xl mt-2">Pilih layanan & durasi</h2>
          </div>
          <button onClick={onClose} className="brutal-sm p-2 bg-white" data-testid="join-modal-close"><Xicon weight="bold" size={20} /></button>
        </div>

        <div className="p-5 md:p-6 space-y-6">
          {loading ? (
            <div className="text-center py-8 font-mono uppercase text-sm text-gray-600">Memuat layanan...</div>
          ) : services.length === 0 ? (
            <div className="text-center py-8 text-gray-600">Belum ada layanan tersedia.</div>
          ) : (
            <>
              <div>
                <div className="font-display font-bold text-lg mb-3">1. Layanan</div>
                <div className="grid sm:grid-cols-2 gap-3" data-testid="join-services">
                  {services.map((s) => {
                    const active = pickedService?.id === s.id;
                    return (
                      <button
                        key={s.id}
                        onClick={() => setPickedService(s)}
                        className={`brutal-sm p-4 text-left transition-transform ${active ? "bg-[#0A0A0A] text-white translate-y-[-2px]" : "bg-white hover:bg-[#FFF8EC]"}`}
                        data-testid={`join-service-${s.slug}`}
                        style={active ? { boxShadow: "6px 6px 0 #FFD60A" } : {}}
                      >
                        <div className="flex items-center gap-3">
                          {s.logo_url && <img src={s.logo_url} alt={s.name} className="w-10 h-10 object-cover border-2 border-black" />}
                          <div className="flex-1">
                            <div className="font-display font-black text-lg">{s.name}</div>
                            <div className={`text-xs font-mono ${active ? "text-gray-300" : "text-gray-600"}`}>
                              {rupiah(s.price_regular)}/bln · min {s.min_duration_months} bln
                            </div>
                          </div>
                          {active && <CheckCircle weight="fill" size={22} />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {pickedService && (
                <div>
                  <div className="font-display font-bold text-lg mb-3">2. Durasi</div>
                  <div className="grid grid-cols-4 gap-2" data-testid="join-durations">
                    {durations.map((m) => {
                      const disabled = m < (pickedService.min_duration_months || 1);
                      const active = duration === m;
                      return (
                        <button
                          key={m}
                          disabled={disabled}
                          onClick={() => setDuration(m)}
                          className={`brutal-sm py-3 font-display font-black text-lg ${disabled ? "bg-gray-100 text-gray-400 cursor-not-allowed" : active ? "bg-[#FF3B30] text-white" : "bg-white"}`}
                          data-testid={`join-duration-${m}`}
                        >
                          {m} bln
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {pickedService && (
                <div className="brutal-sm bg-[#FFD60A]/40 p-4" data-testid="join-summary">
                  <div className="font-mono text-xs uppercase text-gray-700">Total (akan jadi tagihan pending)</div>
                  <div className="font-display font-black text-3xl mt-1">{rupiah(price)}</div>
                  <div className="text-xs text-gray-700 mt-2">
                    Setelah konfirmasi, kamu diarahkan ke tab <b>Pembayaran</b> untuk pilih metode (QRIS manual atau Midtrans otomatis). Admin akan assign kamu ke grup setelah pembayaran diverifikasi.
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="border-t-4 border-black p-4 flex gap-3 justify-end bg-[#FFF8EC]">
          <button onClick={onClose} className="brutal-btn brutal-btn-white" data-testid="join-cancel">Batal</button>
          <button
            onClick={submit}
            disabled={!pickedService || busy}
            className="brutal-btn brutal-btn-red disabled:opacity-50"
            data-testid="join-submit"
          >
            {busy ? "Memproses..." : "Konfirmasi & Buat Tagihan"}
          </button>
        </div>
      </div>
    </div>
  );
}
