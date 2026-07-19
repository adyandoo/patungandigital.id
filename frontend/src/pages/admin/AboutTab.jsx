import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { CheckCircle, Info } from "@phosphor-icons/react";
import { F, Note } from "./shared";

export default function AboutTab() {
  const [data, setData] = useState(null);

  useEffect(() => { api.get("/about").then((r) => setData(r.data)); }, []);
  if (!data) return <div className="brutal p-8">Memuat...</div>;

  const save = async (e) => {
    e.preventDefault();
    try {
      await api.put("/admin/about", {
        hero_title: data.hero_title || "",
        story: data.story || "",
        mission: data.mission || "",
        contact_email: data.contact_email || "",
        contact_whatsapp: data.contact_whatsapp || "",
        contact_address: data.contact_address || "",
      });
      toast.success("Halaman Tentang diperbarui.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <form onSubmit={save} className="max-w-3xl space-y-5" data-testid="about-tab">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="font-display font-bold text-2xl flex items-center gap-2"><Info weight="duotone" /> Halaman Tentang Kami</h2>
        <a href="/about" target="_blank" rel="noreferrer" className="brutal-sm bg-white px-3 py-1 text-xs font-mono uppercase">Buka /about ↗</a>
      </div>

      <Note title="Format Markdown" body="Field 'Cerita' dan 'Misi' mendukung Markdown — heading (## Judul), bold (**tebal**), list (- item), link ([text](url), dll." />

      <div className="brutal p-6 space-y-4">
        <F label="Judul hero (h1)"><input className="brutal-input" value={data.hero_title} onChange={(e) => setData({ ...data, hero_title: e.target.value })} data-testid="about-hero-title" /></F>
        <F label="Cerita (markdown)">
          <textarea rows={8} className="brutal-input font-mono text-sm" value={data.story} onChange={(e) => setData({ ...data, story: e.target.value })} data-testid="about-story" />
        </F>
        <F label="Misi (markdown, opsional)">
          <textarea rows={4} className="brutal-input font-mono text-sm" value={data.mission} onChange={(e) => setData({ ...data, mission: e.target.value })} data-testid="about-mission" />
        </F>
      </div>

      <div className="brutal p-6 space-y-4">
        <h3 className="font-display font-bold text-xl">Kontak</h3>
        <F label="Email"><input type="email" className="brutal-input" value={data.contact_email} onChange={(e) => setData({ ...data, contact_email: e.target.value })} data-testid="about-email" /></F>
        <F label="WhatsApp (contoh 6281234567890)"><input className="brutal-input" value={data.contact_whatsapp} onChange={(e) => setData({ ...data, contact_whatsapp: e.target.value })} data-testid="about-whatsapp" /></F>
        <F label="Alamat (opsional)"><input className="brutal-input" value={data.contact_address} onChange={(e) => setData({ ...data, contact_address: e.target.value })} data-testid="about-address" /></F>
      </div>

      <button type="submit" className="brutal-btn brutal-btn-red" data-testid="about-save">
        <CheckCircle weight="bold" /> Simpan halaman Tentang
      </button>
    </form>
  );
}
