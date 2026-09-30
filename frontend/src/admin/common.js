import { API_BASE } from '../lib/api';

// Shared by the admin screens (ERP-2.0 design system: light cards, one accent colour = amber).
export const inputCls = 'w-full px-3 py-2.5 text-sm bg-gray-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 outline-none transition focus:bg-white focus:ring-2 focus:ring-slate-900/10 focus:border-slate-400 disabled:bg-slate-100 disabled:text-slate-400';
// Single-line inputs and selects.
export const fieldCls = `${inputCls} h-11`;

export const cardCls = 'bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-lg transition-shadow';

const btnBase = 'inline-flex items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
export const btn = {
  primary: `${btnBase} px-4 h-10 bg-amber-700 text-white hover:bg-amber-800`,
  secondary: `${btnBase} px-3.5 h-10 bg-white border border-slate-200 text-slate-600 hover:bg-slate-50`,
  ghost: `${btnBase} px-3 h-10 text-slate-600 hover:bg-slate-100`,
  danger: `${btnBase} px-3.5 h-10 bg-rose-50 text-rose-600 border border-rose-100 hover:bg-rose-600 hover:text-white`,
  small: `${btnBase} px-2.5 h-8 text-xs bg-white border border-slate-200 text-slate-600 hover:bg-slate-50`,
};

export async function api(path, { token, method = 'GET', body } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) {
    const err = new Error(data?.detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

export function downloadJson(filename, data) {
  const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function timeAgo(iso) {
  if (!iso) return '';
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const units = [['year', 31536000], ['month', 2592000], ['day', 86400], ['hour', 3600], ['minute', 60]];
  for (const [unit, size] of units) {
    const n = Math.floor(seconds / size);
    if (n >= 1) return `${n} ${unit}${n > 1 ? 's' : ''} ago`;
  }
  return '';
}

export function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString() : '—';
}
