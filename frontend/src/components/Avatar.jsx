import { useMemo } from "react";

// Deterministic gradient from a string (name or id)
const PALETTES = [
  ["#FF3B30", "#FFD60A"],
  ["#007AFF", "#34C759"],
  ["#FF9500", "#FF3B30"],
  ["#5856D6", "#FF375F"],
  ["#34C759", "#00C7BE"],
  ["#AF52DE", "#FF375F"],
  ["#FF9500", "#FFD60A"],
  ["#5AC8FA", "#5856D6"],
];

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function initials(name) {
  if (!name) return "?";
  const parts = String(name).trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Avatar component. If `src` is provided, renders the image; else generates a
 * gradient chip with initials.
 *
 * Props: src, name, size (px), className, testId
 */
export default function Avatar({ src, name, size = 40, className = "", testId }) {
  const palette = useMemo(() => PALETTES[hashStr(name || "?") % PALETTES.length], [name]);
  const style = {
    width: size,
    height: size,
    background: `linear-gradient(135deg, ${palette[0]}, ${palette[1]})`,
  };
  if (src) {
    return (
      <img
        src={src}
        alt={name || "Avatar"}
        data-testid={testId}
        className={`rounded-full object-cover border-2 border-black ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div
      data-testid={testId}
      className={`rounded-full border-2 border-black flex items-center justify-center text-white font-display font-bold ${className}`}
      style={{ ...style, fontSize: Math.max(12, Math.round(size * 0.4)) }}
    >
      {initials(name)}
    </div>
  );
}
