import { Helmet } from "react-helmet-async";

/** SEO component — sets title, meta description, OpenGraph, Twitter, canonical, optional JSON-LD. */
export default function SEO({
  title,
  description,
  image,
  type = "website",
  canonical,
  jsonLd,
  noindex = false,
}) {
  const siteName = "patungandigital.id";
  const fullTitle = title ? `${title} — ${siteName}` : `${siteName} — Patungan Langganan Digital Premium`;
  const desc = description || "Patungan legal & aman untuk Netflix, Spotify, YouTube dan layanan digital premium lainnya. Bayar setengah harga, tetap dapat akses full.";
  const url = canonical || (typeof window !== "undefined" ? window.location.href : "");
  const imgUrl = image || `${typeof window !== "undefined" ? window.location.origin : ""}/og-default.png`;
  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={desc} />
      {noindex && <meta name="robots" content="noindex, nofollow" />}
      {canonical && <link rel="canonical" href={canonical} />}
      <meta property="og:type" content={type} />
      <meta property="og:site_name" content={siteName} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={desc} />
      {imgUrl && <meta property="og:image" content={imgUrl} />}
      {url && <meta property="og:url" content={url} />}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={desc} />
      {imgUrl && <meta name="twitter:image" content={imgUrl} />}
      {jsonLd && (
        <script type="application/ld+json">
          {JSON.stringify(jsonLd)}
        </script>
      )}
    </Helmet>
  );
}
