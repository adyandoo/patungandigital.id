# Google Search Console — Setup Guide untuk patungandigital.id

Panduan ini membantu Anda submit sitemap dan verifikasi domain di Google Search Console
sehingga blog & halaman utama patungandigital.id cepat ter-index Google.

---

## 1. Verifikasi Domain di Google Search Console

### Cara paling mudah (rekomendasi): HTML Meta Tag

1. Buka **[Google Search Console](https://search.google.com/search-console)** — login dengan akun Google Anda.
2. Klik **Add Property** → pilih **URL prefix** → masukkan `https://patungandigital.id` → **Continue**.
3. Pilih metode verifikasi **HTML tag**. Google akan menampilkan tag seperti:

   ```html
   <meta name="google-site-verification" content="ABC123xyz..." />
   ```

4. Salin **hanya nilai `content`** (mis. `ABC123xyz...`).
5. Tambahkan ke file **`/app/frontend/.env`**:

   ```
   REACT_APP_GSC_VERIFY="ABC123xyz..."
   ```

6. Restart frontend:

   ```bash
   sudo supervisorctl restart frontend
   ```

7. Kembali ke Google Search Console, klik **Verify**.

---

## 2. Submit Sitemap

Sitemap kami dihasilkan otomatis dari database (setiap blog post published masuk otomatis).

### URL Sitemap
```
https://patungandigital.id/api/sitemap.xml
```

### Cara submit
1. Di Google Search Console, sidebar kiri → **Sitemaps**.
2. Masukkan path: `api/sitemap.xml`
3. Klik **Submit**.
4. Status akan berubah jadi **Success** dalam beberapa menit.

Google akan mulai crawl URL-URL:
- `/` (Homepage)
- `/about` (Tentang Kami)
- `/blog` (Blog list)
- `/blog/{slug}` (setiap post yang published)

### Robots.txt
File `robots.txt` sudah tersedia di root domain:
```
https://patungandigital.id/robots.txt
```

Berisi:
- Allow: semua halaman publik
- Disallow: `/admin`, `/dashboard`, `/reset-password`, `/verify-email`, `/auth-callback`
- Referensi Sitemap ke `/api/sitemap.xml`

---

## 3. Tips Agar Cepat Ter-Index

1. **Terbitkan blog konsisten** — minimal 2 post per minggu di 4 minggu pertama.
2. **Gunakan tags yang relevan** — Netflix, Spotify, patungan, tips digital, dll.
3. **Fill excerpt & cover image** setiap post — meta description & OG image tampil di search results.
4. **Blog post kami sudah include JSON-LD Article schema** otomatis (`headline, datePublished, author, keywords`) → berpeluang muncul di rich results Google.
5. **Bagikan link post di WhatsApp/Twitter** — external backlinks mempercepat indexing.

---

## 4. Verifikasi & Monitor

- **Coverage report** di GSC → cek berapa URL sudah ter-index.
- **Performance** → lihat kata kunci apa yang membawa traffic.
- **URL Inspection** → paste URL blog post, klik **Request Indexing** untuk push manual.

---

## 5. Troubleshooting

| Masalah | Solusi |
|---|---|
| Meta verify tidak muncul di source | Pastikan `REACT_APP_GSC_VERIFY` di `.env` frontend, lalu restart frontend. Tag akan muncul di `<head>` semua halaman. |
| Sitemap "couldn't fetch" | Cek `/api/sitemap.xml` accessible via curl. Domain harus HTTPS di production. |
| Google Search Console kosong 2 minggu | Klik **Request Indexing** di URL Inspection untuk blog post individu. Bagikan link ke sosial media. |

---

**Estimasi timeline:**
- Verifikasi: 5 menit
- Submit sitemap: instant
- URL mulai ter-index: 3–7 hari
- Muncul di search results: 2–4 minggu

Semoga sukses! 🚀
