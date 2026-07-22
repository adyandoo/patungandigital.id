import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_API_URL || "https://api.patungandigital.id";
export const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

// Attach bearer token as backup for cross-origin cookie edge cases
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("pd_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default api;

export function formatApiError(detail) {
  if (detail == null) return "Terjadi kesalahan. Coba lagi.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export function rupiah(v) {
  const n = Number(v || 0);
  return "Rp " + n.toLocaleString("id-ID");
}
