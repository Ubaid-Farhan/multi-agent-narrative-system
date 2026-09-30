import { useEffect, useRef, useState } from 'react';
import { MoreHorizontal, X, AlertTriangle, CheckCircle2, Database } from 'lucide-react';
import { btn, cardCls, inputCls } from './common';

// Small building blocks shared by the admin screens.

export function Card({ title, subtitle, actions, children, padded = true, className = '' }) {
  return (
    <section className={`${cardCls} ${padded ? '' : 'overflow-hidden'} ${className}`}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-3 px-6 pt-5 pb-4 border-b border-gray-100">
          <div className="min-w-0">
            {title && <h2 className="text-base font-semibold text-slate-900">{title}</h2>}
            {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </div>
      )}
      <div className={padded ? 'p-6' : ''}>{children}</div>
    </section>
  );
}

export function Field({ label, help, required, htmlFor, children, className = '' }) {
  return (
    <div className={className}>
      {label && (
        <label htmlFor={htmlFor} className="block text-xs font-medium text-slate-700 mb-1.5">
          {label}{required && <span className="text-rose-500 ml-0.5">*</span>}
        </label>
      )}
      {children}
      {help && <p className="text-xs text-slate-500 mt-1.5">{help}</p>}
    </div>
  );
}

export function TextArea({ value, onChange, rows = 4, mono = false, className = '', ...rest }) {
  return (
    <textarea
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      rows={rows}
      spellCheck={!mono}
      className={`${inputCls} ${mono ? 'font-mono text-[13px] leading-relaxed' : 'leading-relaxed'} resize-y ${className}`}
      {...rest}
    />
  );
}

const BADGE_TONES = {
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  amber: 'bg-amber-50 text-amber-800 border-amber-200',
  rose: 'bg-rose-50 text-rose-700 border-rose-200',
  sky: 'bg-sky-50 text-sky-700 border-sky-200',
  violet: 'bg-violet-50 text-violet-700 border-violet-200',
  gray: 'bg-slate-100 text-slate-600 border-slate-200',
};

export function Badge({ tone = 'gray', title, children }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium whitespace-nowrap ${BADGE_TONES[tone] ?? BADGE_TONES.gray}`}>
      {children}
    </span>
  );
}

export function Spinner({ label }) {
  return (
    <div className="flex items-center gap-3 text-sm text-slate-500 py-10 justify-center">
      <span className="h-5 w-5 animate-spin rounded-full border-b-2 border-amber-700" />
      {label}
    </div>
  );
}

export function Notice({ tone, children, onDismiss }) {
  const styles = {
    ok: ['bg-emerald-50 border-emerald-200 text-emerald-800', CheckCircle2],
    error: ['bg-rose-50 border-rose-200 text-rose-700', AlertTriangle],
    warn: ['bg-amber-50 border-amber-200 text-amber-900', Database],
  }[tone];
  const [cls, Icon] = styles;
  return (
    <div className={`flex items-start gap-2.5 rounded-xl border p-3.5 text-sm ${cls}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className="w-4 h-4 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0 break-words">{children}</div>
      {onDismiss && (
        <button type="button" aria-label="Dismiss" onClick={onDismiss} className="p-0.5 rounded opacity-70 hover:opacity-100">
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

export function Modal({ title, subtitle, onClose, closeDisabled, children, footer, size = 'max-w-lg' }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape' && !closeDisabled) onClose(); };
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [onClose, closeDisabled]);
  return (
    <div className="fixed inset-0 z-50 bg-gray-900/40 backdrop-blur-sm flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className={`w-full ${size} bg-white rounded-2xl shadow-xl max-h-[90vh] flex flex-col`}>
        <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4">
          <div>
            <h2 id="modal-title" className="text-lg font-semibold text-slate-900">{title}</h2>
            {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={closeDisabled}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 disabled:opacity-30">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="px-6 pb-6 overflow-y-auto space-y-5">{children}</div>
        {footer && <div className="px-6 py-4 border-t border-gray-100 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

// "⋯" button with a small dropdown. items: [{label, icon, onClick, disabled, danger, title}] or {divider: true}.
export function MoreMenu({ items, label = 'More actions' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen((o) => !o)} className={`${btn.secondary} px-2.5`}>
        <MoreHorizontal className="w-4 h-4" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-60 bg-white rounded-xl border border-gray-100 shadow-xl py-1.5 z-30">
          {items.map((it, i) => (it.divider ? <div key={i} className="my-1.5 border-t border-gray-100" /> : (
            <button key={it.label} type="button" role="menuitem" disabled={it.disabled} title={it.title}
              onClick={() => { setOpen(false); it.onClick(); }}
              className={`w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${it.danger ? 'text-rose-600 hover:bg-rose-50 disabled:hover:bg-transparent' : 'text-slate-700 hover:bg-gray-50 disabled:hover:bg-transparent'}`}>
              {it.icon && <it.icon className="w-4 h-4" />}{it.label}
            </button>
          )))}
        </div>
      )}
    </div>
  );
}

export function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
}
