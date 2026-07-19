import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import api from "@/lib/api";
import SEO from "@/components/SEO";
import { EnvelopeSimple, WhatsappLogo, MapPin, ArrowRight } from "@phosphor-icons/react";

export default function About() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/about").then((r) => setData(r.data)).catch(() => {}); }, []);
  if (!data) return <div className="p-16 text-center">Memuat...</div>;

  return (
    <div className="min-h-screen">
      <SEO
        title={data.hero_title || "Tentang Kami"}
        description={(data.story || "").slice(0, 160).replace(/[#*]/g, "").trim()}
        canonical={typeof window !== "undefined" ? `${window.location.origin}/about` : ""}
      />
      {/* Hero */}
      <section className="border-b-2 border-black bg-[#FFD60A] px-6 md:px-12 py-24 relative overflow-hidden" data-testid="about-hero">
        <div className="absolute inset-0 noise-grid opacity-30"></div>
        <div className="relative z-10 max-w-4xl">
          <span className="pd-tag bg-[#FF3B30] text-white">Tentang Kami</span>
          <h1 className="mt-6 font-display font-black text-5xl md:text-7xl leading-none">{data.hero_title}</h1>
        </div>
      </section>

      {/* Story + Mission */}
      <section className="px-6 md:px-12 py-20 grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
        <div className="md:col-span-2 brutal p-8 md:p-12" data-testid="about-story">
          <div className="pd-tag">Cerita kami</div>
          <div className="prose prose-lg max-w-none mt-4 font-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.story || ""}</ReactMarkdown>
          </div>
        </div>
        <div className="brutal p-8 bg-[#0A0A0A] text-white" data-testid="about-mission">
          <div className="pd-tag bg-white text-black">Misi</div>
          <div className="prose prose-invert mt-4 font-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.mission || ""}</ReactMarkdown>
          </div>
        </div>
      </section>

      {/* Contact */}
      <section className="border-t-2 border-black bg-white px-6 md:px-12 py-20 max-w-6xl mx-auto" data-testid="about-contact">
        <h2 className="font-display font-black text-4xl md:text-5xl">Hubungi kami</h2>
        <div className="mt-8 grid md:grid-cols-3 gap-6">
          {data.contact_email && (
            <a href={`mailto:${data.contact_email}`} className="brutal p-6 hover:translate-y-[-2px] transition-transform">
              <EnvelopeSimple weight="duotone" size={32} />
              <div className="mt-3 font-mono text-xs uppercase text-gray-600">Email</div>
              <div className="font-display font-bold mt-1 break-words">{data.contact_email}</div>
            </a>
          )}
          {data.contact_whatsapp && (
            <a href={`https://wa.me/${data.contact_whatsapp.replace(/[^0-9]/g, "")}`} target="_blank" rel="noreferrer" className="brutal p-6 hover:translate-y-[-2px] transition-transform bg-[#34C759]/20">
              <WhatsappLogo weight="duotone" size={32} />
              <div className="mt-3 font-mono text-xs uppercase text-gray-600">WhatsApp</div>
              <div className="font-display font-bold mt-1">{data.contact_whatsapp}</div>
            </a>
          )}
          {data.contact_address && (
            <div className="brutal p-6">
              <MapPin weight="duotone" size={32} />
              <div className="mt-3 font-mono text-xs uppercase text-gray-600">Alamat</div>
              <div className="font-display font-bold mt-1">{data.contact_address}</div>
            </div>
          )}
        </div>
        <div className="mt-12">
          <Link to="/" className="brutal-btn brutal-btn-red text-lg">Kembali ke Beranda <ArrowRight weight="bold" /></Link>
        </div>
      </section>
    </div>
  );
}
