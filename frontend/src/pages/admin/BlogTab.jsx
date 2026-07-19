import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PlusCircle, PencilSimple, Trash, Newspaper, Eye, X, UploadSimple } from "@phosphor-icons/react";
import { Modal, F } from "./shared";

export default function BlogTab() {
  const [posts, setPosts] = useState([]);
  const [editing, setEditing] = useState(null);
  const [showModal, setShowModal] = useState(false);

  const load = () => api.get("/admin/blog").then((r) => setPosts(r.data)).catch(() => setPosts([]));
  useEffect(() => { load(); }, []);

  const del = async (p) => {
    if (!window.confirm(`Hapus artikel "${p.title}"?`)) return;
    try { await api.delete(`/admin/blog/${p.id}`); toast.success("Artikel dihapus."); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const togglePublish = async (p) => {
    try {
      await api.patch(`/admin/blog/${p.id}`, { published: !p.published });
      toast.success(p.published ? "Artikel jadi draft." : "Artikel ditayangkan.");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div data-testid="blog-tab">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <h2 className="font-display font-bold text-2xl flex items-center gap-2"><Newspaper weight="duotone" /> Blog</h2>
        <div className="flex gap-2">
          <a href="/blog" target="_blank" rel="noreferrer" className="brutal-sm bg-white px-3 py-1 text-xs font-mono uppercase">Buka /blog ↗</a>
          <button onClick={() => { setEditing(null); setShowModal(true); }} className="brutal-btn brutal-btn-red text-sm" data-testid="blog-add">
            <PlusCircle weight="bold" /> Tulis artikel
          </button>
        </div>
      </div>

      {posts.length === 0 && <div className="brutal p-8 text-center text-gray-600">Belum ada artikel.</div>}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {posts.map((p) => (
          <div key={p.id} className="brutal overflow-hidden flex flex-col" data-testid={`blog-item-${p.id}`}>
            {p.cover_image_base64 ? (
              <img src={p.cover_image_base64} alt="" className="w-full h-40 object-cover border-b-2 border-black" />
            ) : (
              <div className="h-40 bg-[#FFD60A] border-b-2 border-black flex items-center justify-center px-4 text-center font-display font-black">{p.title.split(" ").slice(0, 4).join(" ")}</div>
            )}
            <div className="p-4 flex-1 flex flex-col">
              <div className="flex items-center gap-2">
                <span className={`brutal-sm px-2 py-1 text-xs font-mono uppercase ${p.published ? "bg-[#34C759] text-white" : "bg-gray-200"}`}>{p.published ? "Live" : "Draft"}</span>
                {p.tags?.slice(0, 2).map((t) => <span key={t} className="pd-tag text-xs">{t}</span>)}
              </div>
              <h3 className="font-display font-bold text-lg mt-2 leading-tight">{p.title}</h3>
              <div className="text-xs text-gray-600 font-mono mt-1">/{p.slug}</div>
              {p.excerpt && <p className="text-sm text-gray-700 mt-2 line-clamp-3">{p.excerpt}</p>}
              <div className="mt-auto pt-3 flex gap-2 flex-wrap">
                <button onClick={() => { setEditing(p); setShowModal(true); }} className="brutal-sm px-2 py-1 text-xs bg-[#007AFF] text-white" data-testid={`blog-edit-${p.id}`}><PencilSimple weight="bold" /></button>
                <button onClick={() => togglePublish(p)} className="brutal-sm px-2 py-1 text-xs bg-[#FFD60A]" data-testid={`blog-publish-${p.id}`}><Eye weight="bold" /> {p.published ? "Draft" : "Publish"}</button>
                <button onClick={() => del(p)} className="brutal-sm px-2 py-1 text-xs bg-[#FF3B30] text-white" data-testid={`blog-delete-${p.id}`}><Trash weight="bold" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {showModal && <BlogModal post={editing} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function BlogModal({ post, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: post?.title || "",
    slug: post?.slug || "",
    excerpt: post?.excerpt || "",
    content: post?.content || "# Judul artikel\n\nMulai tulis dalam Markdown...",
    cover_image_base64: post?.cover_image_base64 || "",
    tags: (post?.tags || []).join(", "),
    published: post?.published || false,
  });
  const [showPreview, setShowPreview] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    const payload = {
      title: form.title.trim(),
      slug: form.slug.trim() || undefined,
      excerpt: form.excerpt.trim(),
      content: form.content,
      cover_image_base64: form.cover_image_base64 || null,
      tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      published: !!form.published,
    };
    try {
      if (post) {
        await api.patch(`/admin/blog/${post.id}`, payload);
      } else {
        await api.post("/admin/blog", payload);
      }
      toast.success(post ? "Artikel diperbarui." : "Artikel dibuat.");
      onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const uploadCover = async (file) => {
    if (!file) return;
    try {
      const b64 = await new Promise((res, rej) => {
        const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(file);
      });
      setForm({ ...form, cover_image_base64: b64 });
    } catch { toast.error("Gagal baca file"); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="brutal-lg bg-white max-w-4xl w-full max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="blog-modal">
        <div className="border-b-2 border-black p-4 bg-[#FFD60A] flex items-center justify-between sticky top-0 z-10">
          <div className="font-display font-black text-xl">{post ? "Edit Artikel" : "Tulis Artikel Baru"}</div>
          <button onClick={onClose}><X weight="bold" size={24} /></button>
        </div>
        <form onSubmit={save} className="p-6 space-y-4">
          <F label="Judul *"><input required className="brutal-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="blog-title-input" /></F>
          <div className="grid md:grid-cols-2 gap-3">
            <F label="Slug (auto jika kosong)"><input className="brutal-input" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="misal: cara-patungan-netflix" data-testid="blog-slug-input" /></F>
            <F label="Tags (dipisah koma)"><input className="brutal-input" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="netflix, tips, patungan" data-testid="blog-tags-input" /></F>
          </div>
          <F label="Ringkasan (untuk kartu)">
            <textarea rows={2} className="brutal-input" value={form.excerpt} onChange={(e) => setForm({ ...form, excerpt: e.target.value })} maxLength={300} placeholder="Ringkasan singkat 1-2 kalimat..." data-testid="blog-excerpt-input" />
          </F>
          <F label="Cover image (opsional)">
            <div className="flex items-center gap-3 flex-wrap">
              <label className="brutal-btn brutal-btn-blue cursor-pointer text-sm" data-testid="blog-cover-upload">
                <UploadSimple weight="bold" /> Upload cover
                <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadCover(e.target.files[0])} />
              </label>
              {form.cover_image_base64 && (
                <>
                  <img src={form.cover_image_base64} alt="preview" className="h-16 w-24 object-cover border-2 border-black" />
                  <button type="button" onClick={() => setForm({ ...form, cover_image_base64: "" })} className="brutal-sm px-2 py-1 text-xs bg-[#FF3B30] text-white"><Trash weight="bold" /></button>
                </>
              )}
            </div>
          </F>
          <F label={<span className="flex items-center justify-between">Konten (Markdown) <button type="button" onClick={() => setShowPreview(!showPreview)} className="brutal-sm bg-white px-2 py-1 text-xs">{showPreview ? "Edit" : "Preview"}</button></span>}>
            {showPreview ? (
              <div className="brutal-input min-h-[300px] prose max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{form.content}</ReactMarkdown>
              </div>
            ) : (
              <textarea rows={16} className="brutal-input font-mono text-sm" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} data-testid="blog-content-input" />
            )}
          </F>
          <label className="flex items-center gap-2 font-mono text-sm">
            <input type="checkbox" checked={form.published} onChange={(e) => setForm({ ...form, published: e.target.checked })} data-testid="blog-published-checkbox" />
            Tayangkan sekarang (unpublish = tetap draft)
          </label>
          <button type="submit" className="brutal-btn brutal-btn-red w-full justify-center" data-testid="blog-modal-save">
            {post ? "Simpan perubahan" : "Buat artikel"}
          </button>
        </form>
      </div>
    </div>
  );
}
