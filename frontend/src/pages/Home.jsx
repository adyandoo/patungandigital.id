import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { rupiah } from "@/lib/api";
import { UsersThree, Sparkle, ShieldCheck, CurrencyCircleDollar, ArrowRight, Gift, Trophy, Medal, Star, Quotes } from "@phosphor-icons/react";
import Avatar from "@/components/Avatar";
import SEO from "@/components/SEO";
import { useAuth } from "@/context/AuthContext";

const HERO_IMG = "https://images.unsplash.com/photo-1714978444538-9097293e5b20?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDQ2NDF8MHwxfHNlYXJjaHwxfHxncm91cCUyMG9mJTIwZnJpZW5kcyUyMHdhdGNoaW5nJTIwdHYlMjBlbmpveWluZ3xlbnwwfHx8fDE3ODQzODA5MDF8MA&ixlib=rb-4.1.0&q=85";

export default function Home() {
  const { user } = useAuth();
  const [services, setServices] = useState([]);
  const [leaderboard, setLeaderboard] = useState(null);
  const [availability, setAvailability] = useState({});
  const [waitlistFor, setWaitlistFor] = useState(null);
  const [testimonials, setTestimonials] = useState({ items: [], stats: { avg: 0, count: 0 } });

  useEffect(() => {
    api.get("/services").then((r) => setServices(r.data)).catch(() => {});
    api.get("/leaderboard").then((r) => setLeaderboard(r.data)).catch(() => {});
    api.get("/public/availability").then((r) => {
      const map = {};
      r.data.forEach((a) => { map[a.service_id] = a; });
      setAvailability(map);
    }).catch(() => {});
    api.get("/testimonials?limit=12").then((r) => setTestimonials(r.data)).catch(() => {});
  }, []);

  return (
    <div data-testid="home-page">
      <SEO
        title="Patungan Langganan Digital Premium"
        description="Bergabung ke patungan legal untuk Netflix, Spotify, YouTube dan layanan premium lainnya. Bayar setengah harga, tetap dapat akses full. Aman, diatur admin."
      />
      {/* Hero */}
      <section className="px-6 md:px-12 pt-10 md:pt-16 pb-20 noise-grid">
        <div className="grid md:grid-cols-12 gap-8 items-start">
          <div className="md:col-span-7">
            <span className="pd-tag" data-testid="hero-tag">Patungan legal · Indonesia</span>
            <h1 className="mt-6 font-display font-black leading-[0.95] text-5xl md:text-7xl lg:text-8xl">
              Langganan <span className="bg-[#FFD60A] px-2 border-2 border-black">premium</span><br/>
              patungan bareng.
            </h1>
            <p className="mt-6 text-lg md:text-xl max-w-xl text-gray-800">
              Nikmati Netflix, Spotify, YouTube Premium & layanan digital lainnya
              dengan harga jauh lebih murah. Admin kami yang urus semuanya —
              kamu tinggal santai.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <Link to="/register" className="brutal-btn brutal-btn-red" data-testid="hero-cta-register">
                Mulai patungan <ArrowRight weight="bold" />
              </Link>
              <a href="#services" className="brutal-btn brutal-btn-white" data-testid="hero-cta-services">
                Lihat layanan
              </a>
            </div>
            <div className="mt-10 flex flex-wrap gap-6 items-center">
              <StatBox n="1.2rb+" label="Anggota aktif" />
              <StatBox n="15+" label="Layanan siap patungan" />
              <StatBox n="98%" label="Puas & lanjut" />
            </div>
          </div>
          <div className="md:col-span-5 relative">
            <div className="brutal-lg overflow-hidden bg-white">
              <img src={HERO_IMG} alt="Teman nonton bareng" className="w-full h-[420px] object-cover" />
            </div>
            <div className="absolute -bottom-6 -left-6 brutal bg-[#FFD60A] px-4 py-3 rotate-[-4deg]">
              <span className="font-mono text-sm font-bold">HEMAT s.d. 80%</span>
            </div>
            <div className="absolute -top-4 -right-4 brutal bg-[#007AFF] text-white px-4 py-3 rotate-[6deg]">
              <span className="font-mono text-sm font-bold">100% LEGAL</span>
            </div>
          </div>
        </div>
      </section>

      {/* Value props */}
      <section className="border-t-2 border-black bg-white">
        <div className="grid md:grid-cols-3 divide-y-2 md:divide-y-0 md:divide-x-2 divide-black">
          <ValueProp icon={<UsersThree size={40} weight="duotone" />} title="Cukup 1 admin" desc="Kami yang urus akses, host, dan anggota di setiap layanan." />
          <ValueProp icon={<ShieldCheck size={40} weight="duotone" />} title="Langganan resmi" desc="Semua akun premium resmi dari penyedia layanan." />
          <ValueProp icon={<CurrencyCircleDollar size={40} weight="duotone" />} title="Bayar mudah" desc="Payment gateway Midtrans + upload bukti transfer manual." />
        </div>
      </section>

      {/* Services */}
      <section id="services" className="px-6 md:px-12 py-20">
        <div className="flex items-end justify-between mb-10 flex-wrap gap-4">
          <div>
            <span className="pd-tag">Katalog</span>
            <h2 className="font-display font-black text-4xl md:text-6xl mt-4">Layanan siap patungan</h2>
          </div>
          <p className="text-lg max-w-md text-gray-800">Harga per orang per bulan. Durasi minimum berlaku per layanan.</p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8" data-testid="services-grid">
          {services.map((s) => {
            const avail = availability[s.id] || {};
            const filled = avail.filled_slots || 0;
            const total = avail.total_slots || 0;
            const available = avail.available_slots || 0;
            const hasCapacity = total > 0;
            const isFull = hasCapacity && available === 0;
            return (
            <div key={s.id} className="brutal brutal-hover overflow-hidden flex flex-col" data-testid={`service-card-${s.slug}`}>
              <div className="h-40 border-b-2 border-black relative" style={{ background: s.color }}>
                {s.logo_url && <img src={s.logo_url} alt={s.name} className="w-full h-full object-cover mix-blend-multiply opacity-80" />}
                {hasCapacity && (
                  <div className={`absolute top-3 right-3 pd-tag ${isFull ? "bg-[#FF3B30] text-white" : "bg-[#34C759] text-white"}`} data-testid={`slot-badge-${s.slug}`}>
                    {isFull ? "penuh" : `${available} tersedia`}
                  </div>
                )}
              </div>
              <div className="p-6 flex-1 flex flex-col">
                <h3 className="font-display font-bold text-2xl">{s.name}</h3>
                <p className="text-sm text-gray-700 mt-2 flex-1">{s.description}</p>
                {hasCapacity && (
                  <div className="mt-4" data-testid={`slot-bar-${s.slug}`}>
                    <div className="flex items-center justify-between text-xs font-mono uppercase text-gray-700 mb-1">
                      <span>{Math.min(filled, total)}/{total} slot terisi</span>
                      <span>{Math.min(100, Math.round((filled / total) * 100))}%</span>
                    </div>
                    <div className="h-2 border-2 border-black bg-white overflow-hidden">
                      <div className="h-full bg-[#34C759]" style={{ width: `${Math.min(100, Math.round((filled / total) * 100))}%` }}></div>
                    </div>
                  </div>
                )}
                <div className="mt-6 flex items-end justify-between">
                  <div>
                    <div className="font-mono text-xs uppercase text-gray-600">mulai dari</div>
                    <div className="font-display font-black text-3xl">{rupiah(s.price_regular)}<span className="text-sm font-normal">/bln</span></div>
                  </div>
                  <span className="pd-tag">min {s.min_duration_months} bln</span>
                </div>
                {isFull ? (
                  <button onClick={() => setWaitlistFor(s)} className="brutal-btn brutal-btn-yellow mt-6 justify-center" data-testid={`waitlist-cta-${s.slug}`}>
                    Antri di waitlist <Sparkle weight="fill" />
                  </button>
                ) : (
                  <Link
                    to={user ? "/dashboard?action=join" : `/register?service=${s.slug}`}
                    className="brutal-btn brutal-btn-blue mt-6 justify-center"
                    data-testid={`service-cta-${s.slug}`}
                  >
                    Ikut patungan <Sparkle weight="fill" />
                  </Link>
                )}
              </div>
            </div>
          );})}
          {services.length === 0 && (
            <div className="col-span-full text-center py-12 text-gray-600">Belum ada layanan.</div>
          )}
        </div>
      </section>

      {/* Referral Banner */}
      <section className="border-t-2 border-black bg-[#FFD60A] px-6 md:px-12 py-16" data-testid="referral-banner">
        <div className="grid md:grid-cols-12 gap-8 items-center">
          <div className="md:col-span-7">
            <div className="flex items-center gap-3">
              <Gift weight="fill" size={40} />
              <span className="pd-tag bg-black text-white">Program Referral</span>
            </div>
            <h2 className="mt-4 font-display font-black text-4xl md:text-6xl leading-[0.95]">
              Ajak teman.<br/>Kalian <span className="bg-white px-2 border-2 border-black">berdua dapat Rp 10.000</span>.
            </h2>
            <p className="mt-5 text-lg max-w-xl">
              Share kode referralmu ke teman. Setiap teman yang daftar & bayar tagihan pertama, kalian berdua otomatis
              dapat kredit Rp 10.000 yang langsung dipotong dari tagihan berikutnya.
            </p>
            <div className="mt-6 grid grid-cols-3 gap-3 max-w-lg">
              <TierChip n="10" reward="1 bulan gratis" />
              <TierChip n="15" reward="2 bulan gratis" />
              <TierChip n="45" reward="5 bulan gratis" />
            </div>
            <Link to="/register" className="brutal-btn brutal-btn-red mt-8" data-testid="referral-banner-cta">
              Mulai gabung <ArrowRight weight="bold" />
            </Link>
          </div>
          <div className="md:col-span-5">
            {leaderboard && leaderboard.monthly.length > 0 ? (
              <div className="brutal bg-white p-6" data-testid="home-leaderboard">
                <div className="flex items-center gap-2 mb-4">
                  <Trophy weight="fill" size={24} />
                  <div className="font-display font-bold text-xl">Top Referrer bulan ini</div>
                </div>
                <div className="space-y-2">
                  {leaderboard.monthly.slice(0, 5).map((r) => (
                    <div key={r.user_id + r.rank} className="flex items-center justify-between border-b border-black/10 pb-2">
                      <div className="flex items-center gap-3">
                        <span className={`w-8 h-8 flex items-center justify-center font-mono font-black text-sm ${r.rank === 1 ? "bg-[#FFD60A] border-2 border-black" : r.rank === 2 ? "bg-white border-2 border-black" : r.rank === 3 ? "bg-[#FF3B30] text-white border-2 border-black" : "text-gray-600"}`}>
                          {r.rank <= 3 ? <Medal weight="fill" /> : `#${r.rank}`}
                        </span>
                        <div>
                          <div className="font-semibold">{r.name}</div>
                          <div className="text-xs text-gray-600 font-mono">{r.count} teman diajak</div>
                        </div>
                      </div>
                      <div className="text-right font-display font-black">{rupiah(r.total_earned)}</div>
                    </div>
                  ))}
                </div>
                <div className="text-xs text-gray-600 mt-3 font-mono">{leaderboard.month_label}</div>
              </div>
            ) : (
              <div className="brutal bg-white p-6 text-center">
                <Trophy weight="duotone" size={40} className="mx-auto" />
                <div className="font-display font-bold text-xl mt-3">Jadi #1 bulan ini</div>
                <div className="text-sm text-gray-700 mt-2">Belum ada yang mulai — kesempatanmu jadi juara pertama!</div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      {testimonials.items.length > 0 && (
        <section className="border-t-2 border-black bg-white px-6 md:px-12 py-20" data-testid="testimonials-section">
          <div className="flex items-end justify-between gap-6 flex-wrap">
            <div>
              <span className="pd-tag bg-[#34C759] text-white">Testimoni</span>
              <h2 className="font-display font-black text-4xl md:text-6xl mt-4 max-w-3xl">Kata mereka yang<br />sudah patungan.</h2>
            </div>
            <div className="brutal p-4 min-w-[180px] text-center">
              <div className="flex justify-center gap-0.5">
                {[1,2,3,4,5].map((n) => <Star key={n} weight={n <= Math.round(testimonials.stats.avg) ? "fill" : "regular"} size={20} className={n <= Math.round(testimonials.stats.avg) ? "text-[#FFD60A]" : "text-gray-400"} />)}
              </div>
              <div className="font-display font-black text-3xl mt-1" data-testid="testimonials-avg-rating">{testimonials.stats.avg.toFixed(1)}</div>
              <div className="text-xs font-mono uppercase text-gray-600">{testimonials.stats.count} ulasan</div>
            </div>
          </div>
          <div className="mt-12 marquee-wrap">
            <div className="flex gap-6 marquee-track">
              {[...testimonials.items, ...testimonials.items].map((t, i) => (
                <div key={`${t.id}-${i}`} className="brutal p-6 w-80 flex-none bg-[#FFF9E6]" data-testid={`testimonial-${t.id}`}>
                  <Quotes weight="fill" size={28} className="text-[#FF3B30]" />
                  <div className="flex gap-0.5 mt-3">
                    {[1,2,3,4,5].map((n) => <Star key={n} weight={n <= t.rating ? "fill" : "regular"} size={14} className={n <= t.rating ? "text-[#FFD60A]" : "text-gray-400"} />)}
                  </div>
                  <p className="mt-3 text-sm leading-relaxed line-clamp-6">{t.comment}</p>
                  <div className="mt-4 flex items-center gap-3">
                    <Avatar src={t.user?.profile_picture_base64} name={t.user?.name} size={40} />
                    <div className="font-display font-bold">{t.user?.name || "Anonim"}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* How it works */}
      <section className="border-t-2 border-black bg-[#0A0A0A] text-white px-6 md:px-12 py-20">
        <span className="pd-tag bg-[#FFD60A] text-black">Cara kerja</span>
        <h2 className="font-display font-black text-4xl md:text-6xl mt-4 max-w-3xl">Tiga langkah, langsung nikmati.</h2>
        <div className="grid md:grid-cols-3 gap-8 mt-12">
          {[
            { n: "01", t: "Daftar akun", d: "Buat akun di patungandigital.id — gratis, cukup email & WhatsApp." },
            { n: "02", t: "Pilih & bayar", d: "Admin menempatkanmu ke grup layanan. Bayar via Midtrans atau transfer manual." },
            { n: "03", t: "Nikmati premium", d: "Terima kredensial layanan. Selesai." },
          ].map((s) => (
            <div key={s.n} className="border-2 border-white p-6" data-testid={`how-${s.n}`}>
              <div className="font-mono text-[#FFD60A] text-lg">{s.n}</div>
              <div className="font-display font-bold text-2xl mt-2">{s.t}</div>
              <p className="mt-3 text-gray-300">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t-2 border-black px-6 md:px-12 py-10 flex items-center justify-between flex-wrap gap-4">
        <div className="font-display font-black">patungandigital.id © {new Date().getFullYear()}</div>
        <div className="flex gap-4 items-center flex-wrap">
          <Link to="/about" data-testid="footer-about" className="text-sm underline">Tentang Kami</Link>
          <Link to="/blog" data-testid="footer-blog" className="text-sm underline">Blog</Link>
          <div className="text-sm text-gray-700">Hemat itu pintar. Patungan itu keren.</div>
        </div>
      </footer>

      {waitlistFor && <WaitlistModal service={waitlistFor} onClose={() => setWaitlistFor(null)} />}
    </div>
  );
}

function WaitlistModal({ service, onClose }) {
  const [form, setForm] = useState({ email: "", name: "", whatsapp: "", message: "" });
  const [sent, setSent] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/waitlist", { ...form, service_id: service.id });
      setSent(true);
    } catch {}
  };
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="brutal-lg bg-white max-w-md w-full" onClick={(e) => e.stopPropagation()}>
        <div className="border-b-2 border-black bg-[#FFD60A] p-4 font-display font-black text-xl">Waitlist — {service.name}</div>
        {sent ? (
          <div className="p-8 text-center" data-testid="waitlist-thanks">
            <div className="font-display font-black text-2xl">Kamu masuk waitlist! 🎉</div>
            <p className="mt-2 text-gray-700">Admin akan hubungi begitu ada slot kosong. Cek email & WhatsApp ya.</p>
            <button onClick={onClose} className="brutal-btn brutal-btn-red mt-6">Tutup</button>
          </div>
        ) : (
          <form onSubmit={submit} className="p-6 space-y-3" data-testid="waitlist-form">
            <p className="text-sm text-gray-700">Semua slot {service.name} penuh. Isi form ini — admin bakal kabari kalau ada spot kosong.</p>
            <input required type="email" placeholder="Email" className="brutal-input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="waitlist-email" />
            <input placeholder="Nama (opsional)" className="brutal-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input placeholder="WhatsApp (opsional)" className="brutal-input" value={form.whatsapp} onChange={(e) => setForm({ ...form, whatsapp: e.target.value })} />
            <textarea rows="2" placeholder="Pesan (opsional)" className="brutal-input" value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} />
            <button type="submit" className="brutal-btn brutal-btn-red w-full justify-center" data-testid="waitlist-submit">Masuk waitlist</button>
          </form>
        )}
      </div>
    </div>
  );
}

function StatBox({ n, label }) {
  return (
    <div className="brutal-sm bg-white px-4 py-3">
      <div className="font-display font-black text-2xl">{n}</div>
      <div className="text-xs text-gray-700 uppercase font-mono">{label}</div>
    </div>
  );
}

function ValueProp({ icon, title, desc }) {
  return (
    <div className="p-8 md:p-10">
      <div className="w-14 h-14 border-2 border-black flex items-center justify-center bg-[#FFD60A]">
        {icon}
      </div>
      <h3 className="font-display font-bold text-2xl mt-4">{title}</h3>
      <p className="mt-2 text-gray-700">{desc}</p>
    </div>
  );
}

function TierChip({ n, reward }) {
  return (
    <div className="brutal-sm bg-white p-3 text-center">
      <div className="font-display font-black text-2xl">{n}</div>
      <div className="text-[10px] text-gray-700 uppercase font-mono">teman</div>
      <div className="text-xs font-semibold mt-1">{reward}</div>
    </div>
  );
}
