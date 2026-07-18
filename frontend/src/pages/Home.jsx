import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { rupiah } from "@/lib/api";
import { UsersThree, Sparkle, ShieldCheck, CurrencyCircleDollar, ArrowRight } from "@phosphor-icons/react";

const HERO_IMG = "https://images.unsplash.com/photo-1714978444538-9097293e5b20?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDQ2NDF8MHwxfHNlYXJjaHwxfHxncm91cCUyMG9mJTIwZnJpZW5kcyUyMHdhdGNoaW5nJTIwdHYlMjBlbmpveWluZ3xlbnwwfHx8fDE3ODQzODA5MDF8MA&ixlib=rb-4.1.0&q=85";

export default function Home() {
  const [services, setServices] = useState([]);

  useEffect(() => {
    api.get("/services").then((r) => setServices(r.data)).catch(() => {});
  }, []);

  return (
    <div data-testid="home-page">
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
          <ValueProp icon={<CurrencyCircleDollar size={40} weight="duotone" />} title="Bayar mudah" desc="Payment gateway Xendit, tinggal upload bukti transfer." />
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
          {services.map((s) => (
            <div key={s.id} className="brutal brutal-hover overflow-hidden flex flex-col" data-testid={`service-card-${s.slug}`}>
              <div className="h-40 border-b-2 border-black" style={{ background: s.color }}>
                {s.logo_url && <img src={s.logo_url} alt={s.name} className="w-full h-full object-cover mix-blend-multiply opacity-80" />}
              </div>
              <div className="p-6 flex-1 flex flex-col">
                <h3 className="font-display font-bold text-2xl">{s.name}</h3>
                <p className="text-sm text-gray-700 mt-2 flex-1">{s.description}</p>
                <div className="mt-6 flex items-end justify-between">
                  <div>
                    <div className="font-mono text-xs uppercase text-gray-600">mulai dari</div>
                    <div className="font-display font-black text-3xl">{rupiah(s.price_regular)}<span className="text-sm font-normal">/bln</span></div>
                  </div>
                  <span className="pd-tag">min {s.min_duration_months} bln</span>
                </div>
                <Link to="/register" className="brutal-btn brutal-btn-blue mt-6 justify-center" data-testid={`service-cta-${s.slug}`}>
                  Ikut patungan <Sparkle weight="fill" />
                </Link>
              </div>
            </div>
          ))}
          {services.length === 0 && (
            <div className="col-span-full text-center py-12 text-gray-600">Belum ada layanan.</div>
          )}
        </div>
      </section>

      {/* How it works */}
      <section className="border-t-2 border-black bg-[#0A0A0A] text-white px-6 md:px-12 py-20">
        <span className="pd-tag bg-[#FFD60A] text-black">Cara kerja</span>
        <h2 className="font-display font-black text-4xl md:text-6xl mt-4 max-w-3xl">Tiga langkah, langsung nikmati.</h2>
        <div className="grid md:grid-cols-3 gap-8 mt-12">
          {[
            { n: "01", t: "Daftar akun", d: "Buat akun di patungandigital.id — gratis, cukup email & WhatsApp." },
            { n: "02", t: "Pilih & bayar", d: "Admin menempatkanmu ke grup layanan. Bayar via Xendit atau transfer." },
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
        <div className="text-sm text-gray-700">Hemat itu pintar. Patungan itu keren.</div>
      </footer>
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
