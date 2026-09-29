export const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

// Images uploaded from the admin panel are served by the API ("/api/..."); others live in /public.
export function assetUrl(path) {
  if (!path) return "";
  if (/^(https?:|data:|blob:)/.test(path)) return path;
  if (path.startsWith("/api/")) return `${API_BASE}${path}`;
  return path;
}

// Full class strings (Tailwind only generates classes it can see written out).
export const CHARACTER_COLORS = {
  amber:   { bg: "from-amber-500 to-orange-600",  text: "text-amber-900",   bubble: "bg-amber-50 border-amber-300",     swatch: "bg-amber-500" },
  blue:    { bg: "from-blue-600 to-indigo-700",   text: "text-blue-900",    bubble: "bg-blue-50 border-blue-300",       swatch: "bg-blue-600" },
  slate:   { bg: "from-slate-500 to-slate-700",   text: "text-slate-900",   bubble: "bg-slate-50 border-slate-300",     swatch: "bg-slate-500" },
  emerald: { bg: "from-emerald-500 to-teal-600",  text: "text-emerald-900", bubble: "bg-emerald-50 border-emerald-300", swatch: "bg-emerald-500" },
  rose:    { bg: "from-rose-500 to-pink-600",     text: "text-rose-900",    bubble: "bg-rose-50 border-rose-300",       swatch: "bg-rose-500" },
  violet:  { bg: "from-violet-500 to-purple-700", text: "text-violet-900",  bubble: "bg-violet-50 border-violet-300",   swatch: "bg-violet-500" },
  cyan:    { bg: "from-cyan-500 to-sky-600",      text: "text-cyan-900",    bubble: "bg-cyan-50 border-cyan-300",       swatch: "bg-cyan-500" },
  orange:  { bg: "from-orange-500 to-red-600",    text: "text-orange-900",  bubble: "bg-orange-50 border-orange-300",   swatch: "bg-orange-500" },
};

export function colorsFor(name) {
  return CHARACTER_COLORS[name] ?? CHARACTER_COLORS.slate;
}
