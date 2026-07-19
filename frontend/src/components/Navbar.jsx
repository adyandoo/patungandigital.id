import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export default function Navbar() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const authed = user && user !== false;
  const isAdmin = authed && user.role === "admin";

  return (
    <header className="border-b-2 border-black bg-[#F4F3ED] sticky top-0 z-50">
      <div className="px-6 md:px-12 py-4 flex items-center justify-between">
        <Link to="/" data-testid="nav-brand" className="flex items-center gap-2">
          <div className="w-9 h-9 bg-[#FF3B30] border-2 border-black flex items-center justify-center font-display font-black text-white text-lg">P</div>
          <span className="font-display font-black text-xl tracking-tight">patungandigital<span className="text-[#FF3B30]">.id</span></span>
        </Link>
        <nav className="flex items-center gap-3">
          <Link to="/" data-testid="nav-home" className={`hidden md:inline text-sm font-semibold ${loc.pathname === "/" ? "underline decoration-2 underline-offset-4" : ""}`}>Beranda</Link>
          <Link to="/blog" data-testid="nav-blog" className={`hidden md:inline text-sm font-semibold ${loc.pathname.startsWith("/blog") ? "underline decoration-2 underline-offset-4" : ""}`}>Blog</Link>
          <Link to="/about" data-testid="nav-about" className={`hidden md:inline text-sm font-semibold ${loc.pathname === "/about" ? "underline decoration-2 underline-offset-4" : ""}`}>Tentang</Link>
          {authed && !isAdmin && (
            <Link to="/dashboard" data-testid="nav-dashboard" className="hidden md:inline text-sm font-semibold">Dashboard</Link>
          )}
          {isAdmin && (
            <Link to="/admin" data-testid="nav-admin" className="hidden md:inline text-sm font-semibold">Admin</Link>
          )}
          {!authed && (
            <>
              <Link to="/login" data-testid="nav-login" className="brutal-btn brutal-btn-white text-sm">Masuk</Link>
              <Link to="/register" data-testid="nav-register" className="brutal-btn brutal-btn-red text-sm">Daftar</Link>
            </>
          )}
          {authed && (
            <button data-testid="nav-logout" onClick={async () => { await logout(); nav("/"); }} className="brutal-btn brutal-btn-white text-sm">Keluar</button>
          )}
        </nav>
      </div>
    </header>
  );
}
