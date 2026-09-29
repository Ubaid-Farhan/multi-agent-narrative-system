import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen, Users, MessageSquareCode, SlidersHorizontal, Save, Plus, Trash2, LogOut,
  Upload, Play, AlertTriangle, CheckCircle2, Loader2, X, Sparkles,
} from 'lucide-react';
import { API_BASE, assetUrl, CHARACTER_COLORS } from '../lib/api';

const TOKEN_KEY = 'narrative-admin-token';

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (_) { return ''; }
}
function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch (_) {}
}

const PROMPT_INFO = {
  character: { label: 'Character — main prompt', help: 'Wraps every character turn. {persona} is the character\'s persona, {context} is goals/memory/recent dialogue built by the engine.' },
  character_language_urdu: { label: 'Character — Roman Urdu rule', help: 'Inserted as {language_rule} when the story runs in Roman Urdu.' },
  character_language_english: { label: 'Character — English rule', help: 'Inserted as {english_final} when the story runs in English. {english_style} is the character\'s English style.' },
  director_select_speaker: { label: 'Director — pick next speaker', help: 'Runs before every turn: chooses who speaks and writes the scene narration. Story phases live here.' },
  director_twist: { label: 'Director — twist', help: 'Runs once at the twist turn (Settings) to create a dramatic complication.' },
  director_conclusion: { label: 'Director — conclusion check', help: 'Decides whether the story should end and writes the ending.' },
  reviewer_urdu: { label: 'Reviewer — Roman Urdu', help: 'Quality gate after each turn. {character_review_notes} comes from each character\'s review notes.' },
  reviewer_english: { label: 'Reviewer — English', help: 'Same as above, for English mode.' },
  fallback_conclusion: { label: 'Fallback ending text', help: 'Plain text shown if the Director fails to write an ending at max turns. Not a template.' },
};

const SETTINGS_INFO = [
  ['max_turns', 'Max turns', 'Story is forced to end at this turn.'],
  ['min_turns', 'Min turns', 'Story cannot end before this turn.'],
  ['twist_turn', 'Twist turn', 'Turn at which the Director injects a twist.'],
  ['post_twist_turns', 'Turns after twist', 'Minimum turns after the twist before the story may end.'],
  ['min_actions', 'Min physical actions', 'Actions needed before the story may end.'],
  ['max_dialogue_length', 'Max dialogue length', 'Token limit hint for each line of dialogue.'],
  ['temperature', 'Temperature', 'LLM creativity, 0 (strict) to 2 (wild). Default 0.85.'],
];

function slugify(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 64);
}

function placeholdersIn(template) {
  const names = new Set();
  const cleaned = template.replace(/\{\{|\}\}/g, '');
  for (const m of cleaned.matchAll(/\{([^{}]*)\}/g)) names.add(m[1]);
  return [...names];
}

// Trim list items and keywords right before saving (inputs keep raw text while typing).
function normalizeForSave(data) {
  const clean = (list) => (list ?? []).map((x) => String(x).trim()).filter(Boolean);
  return {
    ...data,
    characters: data.characters.map((c) => ({
      ...c,
      goals: clean(c.goals),
      inventory: clean(c.inventory),
      appeals: Object.fromEntries(
        Object.entries(c.appeals ?? {})
          .map(([name, kws]) => [name.trim(), clean(kws)])
          .filter(([name]) => name),
      ),
    })),
  };
}

async function api(path, { token, method = 'GET', body } = {}) {
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

// ───────────────────────────── small UI pieces ─────────────────────────────

const inputCls = 'w-full bg-gray-900 border border-white/15 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:outline-none focus:border-amber-500/70';
const labelCls = 'block text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1.5';

function Field({ label, help, children }) {
  return (
    <div>
      {label && <label className={labelCls}>{label}</label>}
      {children}
      {help && <p className="text-xs text-gray-500 mt-1">{help}</p>}
    </div>
  );
}

function TextArea({ value, onChange, rows = 4, mono = false, ...rest }) {
  return (
    <textarea
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      rows={rows}
      spellCheck={!mono}
      className={`${inputCls} ${mono ? 'font-mono text-[13px] leading-relaxed' : 'leading-relaxed'} resize-y`}
      {...rest}
    />
  );
}

function ImagePicker({ value, onChange, scenarioId, token, onError, tall = false }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const upload = (file) => {
    if (!file) return;
    setBusy(true);
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const res = await api(`/api/admin/scenarios/${scenarioId}/images`, {
          token, method: 'POST', body: { filename: file.name, data: reader.result },
        });
        onChange(res.url);
      } catch (e) {
        onError(e.message);
      } finally {
        setBusy(false);
      }
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="flex gap-3 items-start">
      <div className={`${tall ? 'w-24 h-32' : 'w-40 h-24'} shrink-0 rounded-lg bg-gray-800 border border-white/10 overflow-hidden flex items-center justify-center`}>
        {value ? <img src={assetUrl(value)} alt="" className="w-full h-full object-contain" /> : <span className="text-xs text-gray-500">No image</span>}
      </div>
      <div className="flex-1 space-y-2">
        <input className={inputCls} value={value ?? ''} onChange={(e) => onChange(e.target.value)} placeholder="/img4.png or uploaded URL" />
        <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ''; }} />
        <button type="button" onClick={() => inputRef.current?.click()} disabled={busy}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-xs text-gray-200 disabled:opacity-50">
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
          Upload image
        </button>
      </div>
    </div>
  );
}

// ───────────────────────────── tabs ─────────────────────────────

function StoryTab({ data, update, imageProps, onJsonError }) {
  const [settingText, setSettingText] = useState(() => JSON.stringify(data.setting ?? {}, null, 2));
  const [settingError, setSettingError] = useState('');

  // Text is re-created from saved data on mount, so it is valid again.
  useEffect(() => { onJsonError(false); }, []);

  const changeSetting = (text) => {
    setSettingText(text);
    try {
      const parsed = JSON.parse(text || '{}');
      if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) throw new Error('Must be a JSON object');
      setSettingError('');
      onJsonError(false);
      update((d) => ({ ...d, setting: parsed }));
    } catch (e) {
      setSettingError(e.message);
      onJsonError(true);
    }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="space-y-5">
        <Field label="Status" help="Drafts are hidden from the player until published.">
          <select className={`${inputCls} w-48`} value={data.status ?? 'published'} onChange={(e) => update((d) => ({ ...d, status: e.target.value }))}>
            <option value="published">Published</option>
            <option value="draft">Draft</option>
          </select>
        </Field>
        <Field label="Title"><input className={inputCls} value={data.title ?? ''} onChange={(e) => update((d) => ({ ...d, title: e.target.value }))} /></Field>
        <Field label="Subtitle" help="Shown under the title in the player, e.g. the location.">
          <input className={inputCls} value={data.subtitle ?? ''} onChange={(e) => update((d) => ({ ...d, subtitle: e.target.value }))} />
        </Field>
        <Field label="Story seed / scenario" help="The opening situation. Every agent sees this.">
          <TextArea rows={12} value={data.description} onChange={(v) => update((d) => ({ ...d, description: v }))} />
        </Field>
        <Field label="Background image">
          <ImagePicker {...imageProps} value={data.background_image} onChange={(v) => update((d) => ({ ...d, background_image: v }))} />
        </Field>
      </div>
      <Field label="Setting details (JSON)" help="Location, time, weather, crowd, vehicles… any keys you like.">
        <TextArea rows={22} mono value={settingText} onChange={changeSetting} />
        {settingError && <p className="text-xs text-red-400 mt-1">Invalid JSON: {settingError}</p>}
      </Field>
    </div>
  );
}

function AppealsEditor({ appeals, onChange }) {
  const entries = Object.entries(appeals ?? {});
  const setEntry = (idx, name, keywords) => {
    const next = entries.map((e, i) => (i === idx ? [name, keywords] : e));
    onChange(Object.fromEntries(next));
  };
  return (
    <div className="space-y-2">
      {entries.map(([name, keywords], idx) => (
        <div key={idx} className="grid grid-cols-1 sm:grid-cols-[14rem_1fr_auto] gap-2 items-start">
          <input className={inputCls} value={name} placeholder="Appeal name" aria-label="Appeal name"
            onChange={(e) => setEntry(idx, e.target.value, keywords)} />
          <input className={inputCls} value={keywords.join(',')} placeholder="keyword, another keyword" aria-label="Keywords"
            onChange={(e) => setEntry(idx, name, e.target.value.split(','))} />
          <button type="button" aria-label="Remove appeal" onClick={() => onChange(Object.fromEntries(entries.filter((_, i) => i !== idx)))}
            className="p-2 rounded-lg text-gray-500 hover:text-red-400 hover:bg-white/5"><X className="w-4 h-4" /></button>
        </div>
      ))}
      <button type="button" onClick={() => onChange({ ...appeals, [`New appeal ${entries.length + 1}`]: [] })}
        className="inline-flex items-center gap-1.5 text-xs text-amber-300 hover:text-amber-200"><Plus className="w-3.5 h-3.5" /> Add appeal</button>
    </div>
  );
}

function CharactersTab({ data, update, meta, imageProps }) {
  const [selected, setSelected] = useState(0);
  const chars = data.characters;
  const idx = Math.min(selected, chars.length - 1);
  const c = chars[idx];

  const setChar = (patch) => update((d) => ({
    ...d, characters: d.characters.map((ch, i) => (i === idx ? { ...ch, ...patch } : ch)),
  }));

  const addCharacter = () => {
    const n = chars.length + 1;
    update((d) => ({
      ...d,
      characters: [...d.characters, {
        key: `character_${n}`, name: `New Character ${n}`, label: `New Character ${n}`,
        description: '', goals: [], inventory: [], persona: '', english_style: '', appeals: {},
        review_notes_urdu: '', review_notes_english: '',
        voice: { voice: 'hi-IN-MadhurNeural', rate: '+0%', pitch: '+0Hz' }, image: '', color: 'rose',
      }],
    }));
    setSelected(chars.length);
  };

  const removeCharacter = () => {
    if (chars.length <= 2) return;
    if (!window.confirm(`Remove ${c.name}? This takes effect when you save.`)) return;
    update((d) => ({ ...d, characters: d.characters.filter((_, i) => i !== idx) }));
    setSelected(Math.max(0, idx - 1));
  };

  return (
    <div className="grid lg:grid-cols-[240px_1fr] gap-6">
      <div className="space-y-2">
        {chars.map((ch, i) => (
          <button key={i} type="button" onClick={() => setSelected(i)}
            className={`w-full flex items-center gap-3 p-2.5 rounded-xl border text-left transition-colors ${i === idx ? 'bg-amber-500/10 border-amber-500/50' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}>
            <div className="w-10 h-10 rounded-lg bg-gray-800 overflow-hidden shrink-0">
              {ch.image && <img src={assetUrl(ch.image)} alt="" className="w-full h-full object-contain" />}
            </div>
            <div className="min-w-0">
              <div className={`text-sm font-medium truncate ${i === idx ? 'text-amber-300' : 'text-gray-200'}`}>{ch.name || 'Unnamed'}</div>
              <div className="text-xs text-gray-500 truncate">{ch.label}</div>
            </div>
          </button>
        ))}
        <button type="button" onClick={addCharacter}
          className="w-full inline-flex items-center justify-center gap-1.5 p-2.5 rounded-xl border border-dashed border-white/20 text-sm text-gray-300 hover:bg-white/5">
          <Plus className="w-4 h-4" /> Add character
        </button>
      </div>

      {c && (
        <div className="space-y-6">
          <section className="grid md:grid-cols-3 gap-4">
            <Field label="Name" help="Used in prompts and by the Director.">
              <input className={inputCls} value={c.name} onChange={(e) => setChar({ name: e.target.value })} />
            </Field>
            <Field label="Display label" help="Shown on the character card.">
              <input className={inputCls} value={c.label} onChange={(e) => setChar({ label: e.target.value })} />
            </Field>
            <Field label="Key" help="Internal id (letters, numbers, _).">
              <input className={inputCls} value={c.key} onChange={(e) => setChar({ key: slugify(e.target.value) })} />
            </Field>
          </section>

          <section className="grid md:grid-cols-2 gap-6">
            <Field label="Image">
              <ImagePicker {...imageProps} tall value={c.image} onChange={(v) => setChar({ image: v })} />
            </Field>
            <Field label="Colour">
              <div className="flex flex-wrap gap-2">
                {(meta?.colors ?? Object.keys(CHARACTER_COLORS)).map((col) => (
                  <button key={col} type="button" aria-label={col} title={col} onClick={() => setChar({ color: col })}
                    className={`w-8 h-8 rounded-full ${CHARACTER_COLORS[col]?.swatch ?? 'bg-slate-500'} ${c.color === col ? 'ring-2 ring-offset-2 ring-offset-gray-950 ring-white' : ''}`} />
                ))}
              </div>
            </Field>
          </section>

          <Field label="Short description" help="Seen by the Director and Reviewer (with goals).">
            <TextArea rows={4} value={c.description} onChange={(v) => setChar({ description: v })} />
          </Field>

          <section className="grid md:grid-cols-2 gap-4">
            <Field label="Goals" help="One per line.">
              <TextArea rows={5} value={(c.goals ?? []).join('\n')} onChange={(v) => setChar({ goals: v.split('\n') })} />
            </Field>
            <Field label="Inventory" help="One item per line.">
              <TextArea rows={5} value={(c.inventory ?? []).join('\n')} onChange={(v) => setChar({ inventory: v.split('\n') })} />
            </Field>
          </section>

          <Field label="Persona (deep instructions)" help="The heart of the character: psychology, language, tactics per turn, flaws, how they address others. Goes into {persona}.">
            <TextArea rows={18} mono value={c.persona} onChange={(v) => setChar({ persona: v })} />
          </Field>

          <Field label="English-mode style" help="How this character speaks when the story runs in English. Goes into {english_style}.">
            <TextArea rows={5} mono value={c.english_style} onChange={(v) => setChar({ english_style: v })} />
          </Field>

          <section className="grid md:grid-cols-2 gap-4">
            <Field label="Reviewer notes — Roman Urdu" help="What the Reviewer checks for this character.">
              <TextArea rows={4} value={c.review_notes_urdu} onChange={(v) => setChar({ review_notes_urdu: v })} />
            </Field>
            <Field label="Reviewer notes — English">
              <TextArea rows={4} value={c.review_notes_english} onChange={(v) => setChar({ review_notes_english: v })} />
            </Field>
          </section>

          <Field label="Repeated appeals" help="Keywords that detect a repeated tactic. The more it's used, the more the character is told the crowd is tired of it.">
            <AppealsEditor appeals={c.appeals} onChange={(appeals) => setChar({ appeals })} />
          </Field>

          <section className="grid md:grid-cols-3 gap-4">
            <Field label="TTS voice">
              <select className={inputCls} value={c.voice?.voice ?? ''} onChange={(e) => setChar({ voice: { ...c.voice, voice: e.target.value } })}>
                {[...new Set([c.voice?.voice, ...(meta?.voices ?? [])].filter(Boolean))].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Speed" help="e.g. +15% or -10%">
              <input className={inputCls} value={c.voice?.rate ?? ''} onChange={(e) => setChar({ voice: { ...c.voice, rate: e.target.value } })} />
            </Field>
            <Field label="Pitch" help="e.g. +6Hz or -4Hz">
              <input className={inputCls} value={c.voice?.pitch ?? ''} onChange={(e) => setChar({ voice: { ...c.voice, pitch: e.target.value } })} />
            </Field>
          </section>

          <div className="pt-2 border-t border-white/10">
            <button type="button" onClick={removeCharacter} disabled={chars.length <= 2}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-red-300 hover:bg-red-500/10 disabled:opacity-40 disabled:cursor-not-allowed">
              <Trash2 className="w-4 h-4" /> Remove character
            </button>
            {chars.length <= 2 && <span className="text-xs text-gray-500 ml-2">A story needs at least 2 characters.</span>}
          </div>
        </div>
      )}
    </div>
  );
}

function PromptsTab({ data, update, meta }) {
  const names = Object.keys(meta?.prompts ?? PROMPT_INFO);
  const [selected, setSelected] = useState(names[0]);
  const textRef = useRef(null);
  const spec = meta?.prompts?.[selected] ?? { allowed: [], required: [] };
  const value = data.prompts?.[selected] ?? '';
  const isTemplate = selected !== 'fallback_conclusion';

  const used = isTemplate ? placeholdersIn(value) : [];
  const unknown = used.filter((p) => !spec.allowed.includes(p));
  const missing = spec.required.filter((p) => !used.includes(p));

  const setValue = (v) => update((d) => ({ ...d, prompts: { ...d.prompts, [selected]: v } }));

  const insert = (name) => {
    const el = textRef.current;
    const token = `{${name}}`;
    if (!el) return setValue(value + token);
    const { selectionStart: a, selectionEnd: b } = el;
    setValue(value.slice(0, a) + token + value.slice(b));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(a + token.length, a + token.length); });
  };

  return (
    <div className="grid lg:grid-cols-[260px_1fr] gap-6">
      <div className="space-y-1">
        {names.map((n) => (
          <button key={n} type="button" onClick={() => setSelected(n)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${n === selected ? 'bg-amber-500/15 text-amber-300' : 'text-gray-300 hover:bg-white/5'}`}>
            {PROMPT_INFO[n]?.label ?? n}
          </button>
        ))}
      </div>
      <div className="space-y-3 min-w-0">
        <div>
          <h3 className="text-lg font-semibold text-gray-100">{PROMPT_INFO[selected]?.label ?? selected}</h3>
          <p className="text-sm text-gray-400">{PROMPT_INFO[selected]?.help}</p>
        </div>
        {isTemplate && (
          <div className="rounded-xl bg-white/5 border border-white/10 p-3 space-y-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-gray-400 mr-1">Placeholders (click to insert):</span>
              {spec.allowed.map((p) => (
                <button key={p} type="button" onClick={() => insert(p)}
                  className={`font-mono text-xs px-2 py-0.5 rounded-md border ${spec.required.includes(p) ? 'border-amber-500/50 text-amber-300' : 'border-white/15 text-gray-300'} hover:bg-white/10`}>
                  {`{${p}}`}{spec.required.includes(p) && ' *'}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500">* required. For literal braces in JSON examples write <code className="text-gray-300">{'{{'}</code> and <code className="text-gray-300">{'}}'}</code>.</p>
          </div>
        )}
        {(unknown.length > 0 || missing.length > 0) && (
          <div className="flex items-start gap-2 rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-sm text-red-300">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              {unknown.length > 0 && <div>Unknown placeholder(s): {unknown.map((u) => `{${u}}`).join(', ')}</div>}
              {missing.length > 0 && <div>Missing required: {missing.map((u) => `{${u}}`).join(', ')}</div>}
            </div>
          </div>
        )}
        <textarea ref={textRef} value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false}
          rows={isTemplate ? 32 : 6} className={`${inputCls} font-mono text-[13px] leading-relaxed resize-y`} />
      </div>
    </div>
  );
}

function SettingsTab({ data, update, meta }) {
  const settings = data.settings ?? {};
  const set = (key, v) => update((d) => ({ ...d, settings: { ...d.settings, [key]: v === '' ? '' : Number(v) } }));
  return (
    <div className="max-w-3xl space-y-6">
      <div className="grid sm:grid-cols-2 gap-5">
        {SETTINGS_INFO.map(([key, label, help]) => (
          <Field key={key} label={label} help={`${help}${meta?.default_settings?.[key] !== undefined ? ` Default: ${meta.default_settings[key]}.` : ''}`}>
            <input type="number" step={key === 'temperature' ? 0.05 : 1} min={0} max={key === 'temperature' ? 2 : undefined}
              className={inputCls} value={settings[key] ?? ''} onChange={(e) => set(key, e.target.value)} />
          </Field>
        ))}
      </div>
      <p className="text-xs text-gray-500">The LLM models and API keys stay in the server's <code className="text-gray-300">.env</code> (GEMINI_MODEL, GEMINI_FALLBACK_MODELS, OPENAI_MODEL).</p>
    </div>
  );
}

// ───────────────────────────── login ─────────────────────────────

function Login({ onLogin }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await api('/api/admin/login', { method: 'POST', body: { password } });
      onLogin(res.token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white/5 border border-white/10 rounded-2xl p-8 space-y-5">
        <div>
          <h1 className="text-2xl! leading-tight! font-bold text-amber-300">Admin panel</h1>
          <p className="text-sm text-gray-400 mt-1">Edit stories, characters, personas and prompts.</p>
        </div>
        <Field label="Password">
          <input type="password" autoFocus className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={busy || !password}
          className="w-full py-2.5 rounded-lg bg-linear-to-r from-amber-600 to-orange-600 text-white font-semibold disabled:opacity-50">
          {busy ? 'Checking…' : 'Log in'}
        </button>
        <a href="/" className="block text-center text-xs text-gray-500! hover:text-gray-300!">← Back to story</a>
      </form>
    </div>
  );
}

// ───────────────────────────── New with AI ─────────────────────────────

const EXAMPLE_BRIEFS = [
  'Lahore ki shaadi mein khana waqt se pehle khatam ho gaya — dulhe ka baap, caterer, dulhan ki phuppo aur photographer aamne saamne.',
  'Karachi ke ek flat ki building mein lift phans gayi: landlord, ek naya kirayedar, chowkidar aur ek aunty jo sab jaanti hai.',
  'Islamabad ke petrol pump pe line torne pe jhagra: ek fauji retired colonel, ek food-delivery rider, pump manager aur ek TikToker.',
];

function GenerateDialog({ token, onClose, onCreated }) {
  const [brief, setBrief] = useState('');
  const [count, setCount] = useState(4);
  const [log, setLog] = useState([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const abortRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const run = async () => {
    setRunning(true);
    setError('');
    setLog([]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await fetch(`${API_BASE}/api/admin/scenarios/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ brief, num_characters: count }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        let detail = `Request failed (${res.status})`;
        try { detail = (await res.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          const event = JSON.parse(part.slice(6));
          if (event.type === 'progress') setLog((l) => [...l, event.message]);
          else if (event.type === 'error') throw new Error(event.message);
          else if (event.type === 'done') { onCreated(event); return; }
        }
      }
      throw new Error('The connection closed before the scenario was finished.');
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="gen-title">
      <div className="w-full max-w-2xl bg-gray-900 border border-white/10 rounded-2xl p-6 space-y-5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="gen-title" className="text-xl font-bold text-amber-300 flex items-center gap-2"><Sparkles className="w-5 h-5" /> New scenario with AI</h2>
            <p className="text-sm text-gray-400 mt-1">Describe the scene in a line or two. The AI writes the story seed, setting, characters with deep personas, and adapts every prompt. You add images afterwards.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={running} className="p-1 text-gray-400 hover:text-gray-200 disabled:opacity-30"><X className="w-5 h-5" /></button>
        </div>

        <Field label="Scene idea" help="Roman Urdu or English. Mention who is there and what just happened.">
          <TextArea rows={4} value={brief} onChange={setBrief} disabled={running}
            placeholder="e.g. Karachi ke ek flat ki building mein lift phans gayi…" />
        </Field>
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_BRIEFS.map((b) => (
            <button key={b} type="button" disabled={running} onClick={() => setBrief(b)}
              className="text-left text-xs px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-300 hover:bg-white/10 disabled:opacity-40">
              {b.length > 70 ? `${b.slice(0, 70)}…` : b}
            </button>
          ))}
        </div>
        <Field label="Number of characters">
          <select className={`${inputCls} w-32`} value={count} disabled={running} onChange={(e) => setCount(Number(e.target.value))}>
            {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>

        {(log.length > 0 || running) && (
          <div className="rounded-xl bg-black/40 border border-white/10 p-3 space-y-1.5 text-sm" aria-live="polite">
            {log.map((line, i) => (
              <div key={i} className="flex items-start gap-2 text-gray-300">
                <CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-400 shrink-0" /> {line}
              </div>
            ))}
            {running && <div className="flex items-center gap-2 text-amber-300"><Loader2 className="w-4 h-4 animate-spin" /> Working… this usually takes 1–4 minutes.</div>}
          </div>
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}

        <div className="flex justify-end gap-3">
          <button type="button" onClick={() => (running ? abortRef.current?.abort() : onClose())}
            className="px-4 py-2 rounded-lg text-sm text-gray-300 hover:bg-white/10">{running ? 'Stop' : 'Cancel'}</button>
          <button type="button" onClick={run} disabled={running || brief.trim().length < 10}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-linear-to-r from-amber-600 to-orange-600 text-white text-sm font-semibold disabled:opacity-40">
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} Generate
          </button>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────── main ─────────────────────────────

const TABS = [
  ['story', 'Story', BookOpen],
  ['characters', 'Characters', Users],
  ['prompts', 'Prompts', MessageSquareCode],
  ['settings', 'Settings', SlidersHorizontal],
];

export default function AdminApp() {
  const [token, setToken] = useState(readToken);
  const [meta, setMeta] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [scenarioId, setScenarioId] = useState(null);
  const [data, setData] = useState(null);
  const [savedJson, setSavedJson] = useState('');
  const [tab, setTab] = useState('story');
  const [status, setStatus] = useState(null); // {type: 'ok'|'error', text}
  const [saving, setSaving] = useState(false);
  const [jsonError, setJsonError] = useState(false);
  const [showGenerate, setShowGenerate] = useState(false);

  const dirty = data !== null && JSON.stringify(data) !== savedJson;

  const logout = () => { writeToken(''); setToken(''); };
  const handleError = (e) => {
    if (e.status === 401) logout();
    setStatus({ type: 'error', text: e.message });
  };

  const loadList = async () => {
    const res = await api('/api/admin/scenarios', { token });
    setScenarios(res.scenarios ?? []);
    return res;
  };

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        setMeta(await api('/api/admin/meta', { token }));
        const res = await loadList();
        setScenarioId((cur) => cur ?? res.default ?? res.scenarios?.[0]?.id ?? null);
      } catch (e) { handleError(e); }
    })();
  }, [token]);

  useEffect(() => {
    if (!token || !scenarioId) return;
    (async () => {
      try {
        const res = await api(`/api/admin/scenarios/${scenarioId}`, { token });
        setData(res);
        setSavedJson(JSON.stringify(res));
        setJsonError(false);
      } catch (e) { handleError(e); }
    })();
  }, [token, scenarioId]);

  useEffect(() => {
    const warn = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const imageProps = useMemo(() => ({
    scenarioId, token, onError: (msg) => setStatus({ type: 'error', text: msg }),
  }), [scenarioId, token]);

  if (!token) return <Login onLogin={(t) => { writeToken(t); setToken(t); setStatus(null); }} />;

  const confirmDiscard = () => !dirty || window.confirm('You have unsaved changes. Discard them?');

  const switchScenario = (id) => {
    if (id === scenarioId || !confirmDiscard()) return;
    setData(null);
    setStatus(null);
    setScenarioId(id);
  };

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const res = await api(`/api/admin/scenarios/${scenarioId}`, { token, method: 'PUT', body: normalizeForSave(data) });
      setData(res);
      setSavedJson(JSON.stringify(res));
      await loadList();
      setStatus({ type: 'ok', text: 'Saved. The next story run uses these changes.' });
    } catch (e) { handleError(e); } finally { setSaving(false); }
  };

  const createScenario = async () => {
    if (!confirmDiscard()) return;
    const title = window.prompt(`New scenario title (it starts as a copy of "${data?.title ?? 'current scenario'}"):`);
    if (!title) return;
    const id = slugify(title);
    if (!id) return setStatus({ type: 'error', text: 'Title needs at least one letter or number.' });
    try {
      await api('/api/admin/scenarios', { token, method: 'POST', body: { id, title, copy_from: scenarioId } });
      await loadList();
      setData(null);
      setScenarioId(id);
      setTab('story');
      setStatus({ type: 'ok', text: `Created "${title}". Edit it and press Save.` });
    } catch (e) { handleError(e); }
  };

  const onGenerated = async (event) => {
    setShowGenerate(false);
    await loadList();
    setData(null);
    setScenarioId(event.id);
    setTab('story');
    const extra = event.warnings?.length ? ` Note: ${event.warnings.join(' ')}` : '';
    setStatus({ type: event.warnings?.length ? 'error' : 'ok',
      text: `Draft “${event.title}” created. Review it, add images, set Status to Published and Save.${extra}` });
  };

  const deleteScenario = async () => {
    if (!window.confirm(`Delete "${data?.title}" permanently? Its images are deleted too. This cannot be undone.`)) return;
    try {
      await api(`/api/admin/scenarios/${scenarioId}`, { token, method: 'DELETE' });
      const res = await loadList();
      setData(null);
      setSavedJson('');
      setScenarioId(res.default ?? res.scenarios?.[0]?.id ?? null);
      setStatus({ type: 'ok', text: 'Scenario deleted.' });
    } catch (e) { handleError(e); }
  };

  const update = (fn) => setData((d) => fn(d));
  const isDefault = scenarioId === 'rickshaw_accident';

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {showGenerate && <GenerateDialog token={token} onClose={() => setShowGenerate(false)} onCreated={onGenerated} />}
      <header className="sticky top-0 z-20 bg-gray-950/95 backdrop-blur border-b border-white/10">
        <div className="px-4 md:px-6 py-3 flex flex-wrap items-center gap-3">
          <span className="text-lg font-bold text-amber-300 mr-2">Narrative Admin</span>
          <label htmlFor="admin-scenario" className="sr-only">Scenario</label>
          <select id="admin-scenario" value={scenarioId ?? ''} onChange={(e) => switchScenario(e.target.value)}
            className="bg-gray-900 border border-white/15 rounded-lg px-3 py-1.5 text-sm min-w-48">
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.title}{s.status === 'draft' ? ' (draft)' : ''}</option>)}
          </select>
          <button type="button" onClick={createScenario} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-sm">
            <Plus className="w-4 h-4" /> New
          </button>
          <button type="button" onClick={() => confirmDiscard() && setShowGenerate(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 text-sm">
            <Sparkles className="w-4 h-4" /> New with AI
          </button>
          <button type="button" onClick={deleteScenario} disabled={isDefault || !data} title={isDefault ? 'The default scenario cannot be deleted' : 'Delete scenario'}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-red-300 hover:bg-red-500/10 disabled:opacity-30 disabled:cursor-not-allowed">
            <Trash2 className="w-4 h-4" /> Delete
          </button>
          <div className="flex-1" />
          <a href="/" onClick={(e) => { if (!confirmDiscard()) e.preventDefault(); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-gray-300! hover:bg-white/10">
            <Play className="w-4 h-4" /> Open player
          </a>
          <button type="button" onClick={save} disabled={!dirty || saving || jsonError}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-linear-to-r from-amber-600 to-orange-600 text-white text-sm font-semibold disabled:opacity-40">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {dirty ? 'Save changes' : 'Saved'}
          </button>
          <button type="button" onClick={() => confirmDiscard() && logout()} aria-label="Log out" title="Log out"
            className="p-2 rounded-lg text-gray-400 hover:text-gray-200 hover:bg-white/10"><LogOut className="w-4 h-4" /></button>
        </div>
        <nav className="px-4 md:px-6 flex gap-1 overflow-x-auto [scrollbar-width:none]">
          {TABS.map(([key, label, Icon]) => (
            <button key={key} type="button" onClick={() => setTab(key)}
              className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-sm border-b-2 -mb-px whitespace-nowrap ${tab === key ? 'border-amber-500 text-amber-300' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </nav>
      </header>

      {status && (
        <div className={`mx-4 md:mx-6 mt-4 flex items-start gap-2 rounded-lg p-3 text-sm ${status.type === 'ok' ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300' : 'bg-red-500/10 border border-red-500/30 text-red-300'}`}>
          {status.type === 'ok' ? <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" /> : <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />}
          <span className="flex-1">{status.text}</span>
          <button type="button" aria-label="Dismiss" onClick={() => setStatus(null)}><X className="w-4 h-4" /></button>
        </div>
      )}

      <main className="px-4 md:px-6 py-6">
        {!data ? (
          <div className="flex items-center gap-2 text-gray-400"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
        ) : (
          <div key={scenarioId}>
            {tab === 'story' && <StoryTab data={data} update={update} imageProps={imageProps} onJsonError={setJsonError} />}
            {tab === 'characters' && <CharactersTab data={data} update={update} meta={meta} imageProps={imageProps} />}
            {tab === 'prompts' && <PromptsTab data={data} update={update} meta={meta} />}
            {tab === 'settings' && <SettingsTab data={data} update={update} meta={meta} />}
          </div>
        )}
      </main>
    </div>
  );
}
