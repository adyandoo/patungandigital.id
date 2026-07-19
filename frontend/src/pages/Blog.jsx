import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import api from "@/lib/api";
import { ArrowLeft, Calendar, Tag as TagIcon, User } from "@phosphor-icons/react";

export function BlogList() {
  const [data, setData] = useState({ items: [], total: 0, tags: [] });
  const [tag, setTag] = useState("");

  const load = () => {
    const q = tag ? `?tag=${encodeURIComponent(tag)}&limit=30` : "?limit=30";
    api.get(`/blog${q}`).then((r) => setData(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [tag]);

  return (
    <div className="min-h-screen">
      <section className="border-b-2 border-black bg-[#0A0A0A] text-white px-6 md:px-12 py-20">
        <span className="pd-tag bg-[#FFD60A] text-black">Blog</span>
        <h1 className="mt-6 font-display font-black text-5xl md:text-7xl leading-none">Cerita, tips,<br />& kabar terbaru.</h1>
        <p className="mt-6 text-white/70 max-w-2xl">Rekomendasi patungan, ulasan layanan, dan pengumuman dari tim patungandigital.id.</p>
      </section>

      {data.tags.length > 0 && (
        <div className="px-6 md:px-12 py-6 border-b-2 border-black bg-white flex gap-2 flex-wrap items-center" data-testid="blog-tag-cloud">
          <span className="font-mono text-xs uppercase text-gray-600 mr-2">Topik:</span>
          <button onClick={() => setTag("")} className={`brutal-sm px-3 py-1 text-xs uppercase font-mono ${!tag ? "bg-black text-white" : "bg-white"}`}>Semua</button>
          {data.tags.map((t) => (
            <button key={t.tag} onClick={() => setTag(t.tag)} data-testid={`blog-tag-${t.tag}`} className={`brutal-sm px-3 py-1 text-xs uppercase font-mono ${tag === t.tag ? "bg-black text-white" : "bg-white"}`}>
              {t.tag} <span className="opacity-60">{t.count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="px-6 md:px-12 py-16 max-w-6xl mx-auto">
        {data.items.length === 0 ? (
          <div className="brutal p-12 text-center text-gray-600" data-testid="blog-empty">Belum ada artikel. Kembali lagi nanti ya!</div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8" data-testid="blog-grid">
            {data.items.map((p) => (
              <Link key={p.id} to={`/blog/${p.slug}`} className="brutal hover:translate-y-[-2px] transition-transform bg-white flex flex-col" data-testid={`blog-card-${p.id}`}>
                {p.cover_image_base64 ? (
                  <img src={p.cover_image_base64} alt="" className="w-full aspect-[3/2] object-cover border-b-2 border-black" />
                ) : (
                  <div className="w-full aspect-[3/2] bg-[#FFD60A] border-b-2 border-black flex items-center justify-center">
                    <div className="font-display font-black text-4xl px-4 text-center">{p.title.split(" ").slice(0, 3).join(" ")}</div>
                  </div>
                )}
                <div className="p-5 flex-1 flex flex-col">
                  <div className="flex flex-wrap gap-1">
                    {(p.tags || []).slice(0, 3).map((t) => <span key={t} className="pd-tag bg-white text-xs">{t}</span>)}
                  </div>
                  <h3 className="mt-3 font-display font-bold text-xl leading-tight">{p.title}</h3>
                  {p.excerpt && <p className="mt-2 text-sm text-gray-700 line-clamp-3">{p.excerpt}</p>}
                  <div className="mt-auto pt-4 flex items-center gap-4 text-xs text-gray-600 font-mono">
                    <span className="flex items-center gap-1"><Calendar size={14} /> {p.published_at ? new Date(p.published_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" }) : ""}</span>
                    {p.author_name && <span className="flex items-center gap-1"><User size={14} /> {p.author_name}</span>}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function BlogPost() {
  const { slug } = useParams();
  const nav = useNavigate();
  const [post, setPost] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    api.get(`/blog/${slug}`).then((r) => setPost(r.data)).catch(() => setNotFound(true));
  }, [slug]);

  if (notFound) return (
    <div className="p-16 text-center max-w-md mx-auto">
      <h2 className="font-display font-black text-3xl">Artikel tidak ditemukan.</h2>
      <button onClick={() => nav("/blog")} className="brutal-btn brutal-btn-red mt-8"><ArrowLeft weight="bold" /> Kembali ke Blog</button>
    </div>
  );
  if (!post) return <div className="p-16 text-center">Memuat...</div>;

  return (
    <article className="min-h-screen" data-testid="blog-post">
      <div className="border-b-2 border-black bg-[#FFD60A] px-6 md:px-12 py-16">
        <div className="max-w-3xl mx-auto">
          <Link to="/blog" className="inline-flex items-center gap-2 font-mono text-sm underline" data-testid="blog-back-link"><ArrowLeft weight="bold" /> Semua artikel</Link>
          <div className="mt-6 flex flex-wrap gap-2">
            {(post.tags || []).map((t) => <span key={t} className="pd-tag bg-white">{t}</span>)}
          </div>
          <h1 className="mt-4 font-display font-black text-4xl md:text-6xl leading-none">{post.title}</h1>
          <div className="mt-6 flex items-center gap-4 text-sm font-mono">
            {post.author_name && <span className="flex items-center gap-1"><User size={16} /> {post.author_name}</span>}
            {post.published_at && <span className="flex items-center gap-1"><Calendar size={16} /> {new Date(post.published_at).toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })}</span>}
          </div>
        </div>
      </div>
      {post.cover_image_base64 && (
        <div className="border-b-2 border-black">
          <img src={post.cover_image_base64} alt={post.title} className="w-full max-h-[500px] object-cover" />
        </div>
      )}
      <div className="px-6 md:px-12 py-16 max-w-3xl mx-auto">
        <div className="prose prose-lg max-w-none font-body" data-testid="blog-post-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{post.content}</ReactMarkdown>
        </div>
      </div>
    </article>
  );
}
