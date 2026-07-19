import { useEffect, useState } from "react";
import api, { rupiah, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Receipt, User, Lock, Ticket, UploadSimple, CheckCircle, ClockCounterClockwise, Gift, Copy, ShareNetwork, Trophy, Medal, Circle, CheckFat, Sparkle } from "@phosphor-icons/react";

export default function UserDashboard() {
  const { user, setUser } = useAuth();
  const [tab, setTab] = useState("subs");
  const [subs, setSubs] = useState([]);
  const [payments, setPayments] = useState([]);
  const [onboarding, setOnboarding] = useState(null);

  const loadAll = async () => {
    try {
      const [s, p, o] = await Promise.all([
        api.get("/me/subscriptions"),
        api.get("/me/payments"),
        api.get("/me/onboarding"),
      ]);
      setSubs(s.data);
      setPayments(p.data);
      setOnboarding(o.data);
    } catch {}
  };

  useEffect(() => { loadAll(); }, []);

  return (
    <div className="px-6 md:px-12 py-10">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <span className="pd-tag">Dashboard</span>
          <h1 className="font-display font-black text-4xl md:text-5xl mt-3">Halo, {user?.name}.</h1>
          <p className="text-gray-700 mt-1">Semua urusan patunganmu ada di sini.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <StatChip label="Langganan aktif" value={subs.filter((s) => s.status === "active").length} />
          <StatChip label="Tagihan" value={payments.filter((p) => p.status === "pending").length} />
          {user?.referral_credit > 0 && (
            <StatChip label="Kredit referral" value={rupiah(user.referral_credit)} />
          )}
        </div>
      </div>

      {/* Onboarding checklist */}
      {onboarding && onboarding.completed < onboarding.total && (
        <OnboardingCard data={onboarding} goToTab={setTab} />
      )}

      {/* Tabs */}
      <div className="mt-8 flex gap-2 border-b-2 border-black overflow-x-auto">
        <TabBtn active={tab === "subs"} onClick={() => setTab("subs")} icon={<Ticket weight="duotone" />} label="Langganan" testid="tab-subs" />
        <TabBtn active={tab === "payments"} onClick={() => setTab("payments")} icon={<Receipt weight="duotone" />} label="Pembayaran" testid="tab-payments" />
        <TabBtn active={tab === "referral"} onClick={() => setTab("referral")} icon={<Gift weight="duotone" />} label="Referral" testid="tab-referral" />
        <TabBtn active={tab === "profile"} onClick={() => setTab("profile")} icon={<User weight="duotone" />} label="Profil" testid="tab-profile" />
        <TabBtn active={tab === "password"} onClick={() => setTab("password")} icon={<Lock weight="duotone" />} label="Password" testid="tab-password" />
      </div>

      <div className="mt-8">
        {tab === "subs" && <SubsPanel subs={subs} />}
        {tab === "payments" && <PaymentsPanel payments={payments} reload={loadAll} />}
        {tab === "referral" && <ReferralPanel />}
        {tab === "profile" && <ProfilePanel user={user} setUser={setUser} />}
        {tab === "password" && <PasswordPanel />}
      </div>
    </div>
  );
}

function OnboardingCard({ data, goToTab }) {
  const nextAction = {
    profile: { tab: "profile", label: "Isi WhatsApp sekarang" },
    first_payment: { tab: "payments", label: "Lihat tagihan" },
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
          onClick={() => goToTab(next.tab)}
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

function SubsPanel({ subs }) {
  if (subs.length === 0) return <EmptyState msg="Belum ada langganan. Admin akan menambahkanmu ke grup layanan setelah pembayaran." />;
  return (
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
  );
}

function PaymentsPanel({ payments, reload }) {
  const [uploadingId, setUploadingId] = useState(null);

  const upload = async (paymentId, file) => {
    setUploadingId(paymentId);
    try {
      const b64 = await toBase64(file);
      await api.post(`/me/payments/${paymentId}/receipt`, {
        payment_id: paymentId,
        file_base64: b64,
        file_name: file.name,
      });
      toast.success("Bukti transfer diunggah!");
      reload();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setUploadingId(null);
    }
  };

  if (payments.length === 0) return <EmptyState msg="Belum ada tagihan." />;
  return (
    <div className="space-y-4" data-testid="payments-list">
      {payments.map((p) => (
        <div key={p.id} className="brutal p-6 md:p-8 grid md:grid-cols-4 gap-4" data-testid={`payment-card-${p.id}`}>
          <div>
            <div className="font-mono text-xs uppercase text-gray-600">Layanan</div>
            <div className="font-display font-bold text-xl">{p.service_name}</div>
            <div className="text-sm text-gray-600 mt-1">{p.period_label}</div>
          </div>
          <div>
            <div className="font-mono text-xs uppercase text-gray-600">Jumlah</div>
            <div className="font-display font-black text-2xl">{rupiah(p.amount)}</div>
            {p.due_date && <div className="text-sm text-gray-600">Jatuh tempo {formatDate(p.due_date)}</div>}
          </div>
          <div>
            <div className="font-mono text-xs uppercase text-gray-600">Status</div>
            <StatusPill status={p.status} />
            {p.receipt && (
              <div className="text-xs text-gray-600 mt-2">
                <ClockCounterClockwise size={14} className="inline" /> Bukti diunggah {formatDateTime(p.receipt.uploaded_at)}
              </div>
            )}
          </div>
          <div className="flex flex-col items-start gap-2">
            {p.midtrans_redirect_url && (
              <a href={p.midtrans_redirect_url} target="_blank" rel="noreferrer" className="brutal-btn brutal-btn-blue text-sm" data-testid={`pay-midtrans-${p.id}`}>Bayar via Midtrans</a>
            )}
            {!p.midtrans_redirect_url && p.xendit_invoice_url && (
              <a href={p.xendit_invoice_url} target="_blank" rel="noreferrer" className="brutal-btn brutal-btn-blue text-sm">Bayar via Xendit</a>
            )}
            <label className="brutal-btn brutal-btn-yellow text-sm cursor-pointer" data-testid={`upload-receipt-${p.id}`}>
              <UploadSimple weight="bold" />
              {uploadingId === p.id ? "Mengunggah..." : p.receipt ? "Ganti bukti" : "Upload bukti"}
              <input type="file" accept="image/*,application/pdf" className="hidden" onChange={(e) => e.target.files[0] && upload(p.id, e.target.files[0])} />
            </label>
          </div>
        </div>
      ))}
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
    <form onSubmit={save} className="brutal p-6 md:p-10 max-w-2xl" data-testid="profile-form">
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
