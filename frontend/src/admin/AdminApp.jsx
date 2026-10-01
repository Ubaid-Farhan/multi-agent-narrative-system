import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen, Users, MessageSquareCode, SlidersHorizontal, Save, Plus, Trash2, LogOut, Upload, Play,
  CheckCircle2, Loader2, X, Sparkles, History, Download, FileUp, Library, Menu, Search, ImageOff, Braces, List, Wand2,
  Image as ImageIcon,
} from 'lucide-react';
import { API_BASE, assetUrl, CHARACTER_COLORS } from '../lib/api';
import { api, inputCls, fieldCls, btn, downloadJson, formatDate, timeAgo, initials } from './common';
import { Card, Field, TextArea, Badge, Notice, Modal, MoreMenu, Skeleton, SkeletonCard, SkeletonRows, SkeletonHeader } from './ui';
import RunsView from './RunsView';

const TOKEN_KEY = 'narrative-admin-token';
const FONT = "'Roboto Flex', system-ui, -apple-system, 'Segoe UI', sans-serif";

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (_) { return ''; }
}
function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch (_) {}
}

// Roboto Flex is the platform font; only the admin loads it.
function useAdminFont() {
  useEffect(() => {
    if (document.getElementById('admin-font')) return;
    const link = document.createElement('link');
    link.id = 'admin-font';
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=Roboto+Flex:opsz,wght@8..144,300..700&display=swap';
    document.head.appendChild(link);
  }, []);
}

const PROMPT_INFO = {
  character: { group: 'Character', label: 'Main prompt', help: 'Wraps every character turn. {persona} is the character\'s persona, {context} is goals/memory/recent dialogue built by the engine.' },
  character_language_urdu: { group: 'Character', label: 'Roman Urdu rule', help: 'Inserted as {language_rule} when the story runs in Roman Urdu.' },
  character_language_english: { group: 'Character', label: 'English rule', help: 'Inserted as {english_final} when the story runs in English. {english_style} is the character\'s English style.' },
  director_select_speaker: { group: 'Director', label: 'Pick next speaker', help: 'Runs before every turn: chooses who speaks and writes the scene narration. Story phases live here.' },
  director_twist: { group: 'Director', label: 'Twist', help: 'Runs once at the twist turn (Settings) to create a dramatic complication.' },
  director_conclusion: { group: 'Director', label: 'Conclusion check', help: 'Decides whether the story should end and writes the ending.' },
  reviewer_urdu: { group: 'Reviewer', label: 'Roman Urdu', help: 'Quality gate after each turn. {character_review_notes} comes from each character\'s review notes.' },
  reviewer_english: { group: 'Reviewer', label: 'English', help: 'Same as above, for English mode.' },
  fallback_conclusion: { group: 'Other', label: 'Fallback ending text', help: 'Plain text shown if the Director fails to write an ending at max turns. Not a template.' },
};
const PROMPT_GROUPS = ['Character', 'Director', 'Reviewer', 'Other'];

const SETTINGS_GROUPS = [
  ['Story length', 'When the story is allowed to end.', [
    ['max_turns', 'Max turns', 'Story is forced to end at this turn.'],
    ['min_turns', 'Min turns', 'Story cannot end before this turn.'],
    ['min_actions', 'Min physical actions', 'Actions needed before the story may end.'],
  ]],
  ['Twist', 'The Director\'s dramatic complication.', [
    ['twist_turn', 'Twist turn', 'Turn at which the Director injects a twist.'],
    ['post_twist_turns', 'Turns after twist', 'Minimum turns after the twist before the story may end.'],
  ]],
  ['Generation', 'How each line is written.', [
    ['max_dialogue_length', 'Max dialogue length', 'Token limit hint for each line of dialogue.'],
    ['temperature', 'Temperature', 'LLM creativity, 0 (strict) to 2 (wild).'],
  ]],
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

function promptProblems(name, value, spec) {
  if (name === 'fallback_conclusion' || !spec) return { unknown: [], missing: [] };
  const used = placeholdersIn(value ?? '');
  return {
    unknown: used.filter((p) => !spec.allowed.includes(p)),
    missing: spec.required.filter((p) => !used.includes(p)),
  };
}

// The parts of the (possibly unsaved) scenario the image prompt is written from.
function scenarioForPrompt(data) {
  return { title: data.title, subtitle: data.subtitle, description: data.description, setting: data.setting };
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

// ───────────────────────────── images ─────────────────────────────

// Asks the image model for a picture: shows the suggested prompt (editable), a preview, and "Use this image".
function ImageGenDialog({ scenarioId, token, request, portrait, onUse, onClose }) {
  const [prompt, setPrompt] = useState('');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/api/admin/images/prompt', { token, method: 'POST', body: request })
      .then((r) => setPrompt(r.prompt)).catch((e) => setError(e.message));
  }, []);

  const generate = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await api(`/api/admin/scenarios/${scenarioId}/images/generate`, { token, method: 'POST', body: { prompt, target: request.target } });
      setUrl(res.url);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const who = request.target === 'character' ? request.character?.name || 'this character' : 'the scene background';
  return (
    <Modal size="max-w-3xl" title={`Generate image for ${who}`} onClose={onClose} closeDisabled={busy}
      subtitle="The prompt is written from the scenario. Edit it if you like, then generate. Each try uses a little of the free daily limit."
      footer={(
        <>
          <button type="button" onClick={onClose} disabled={busy} className={btn.secondary}>Cancel</button>
          <button type="button" onClick={generate} disabled={busy || !prompt.trim()} className={url ? btn.secondary : btn.primary}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />} {busy ? 'Generating…' : url ? 'Try again' : 'Generate'}
          </button>
          {url && <button type="button" disabled={busy} onClick={() => onUse(url)} className={btn.primary}><CheckCircle2 className="w-4 h-4" /> Use this image</button>}
        </>
      )}>
      <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_16rem]">
        <Field label="Prompt" htmlFor="img-prompt" help="English works best. Describe look, clothes, mood and style.">
          {prompt || error ? <TextArea id="img-prompt" rows={12} value={prompt} onChange={setPrompt} disabled={busy} /> : <Skeleton className="h-72 w-full" />}
        </Field>
        <div>
          <div className="text-xs font-medium text-slate-700 mb-1.5">Preview</div>
          <div className={`${portrait ? 'aspect-[3/4]' : 'aspect-square'} w-full rounded-xl bg-gray-50 border border-slate-200 overflow-hidden flex items-center justify-center`}>
            {busy ? <Skeleton className="w-full h-full rounded-none" />
              : url ? <LoadingImage src={assetUrl(url)} className="w-full h-full object-cover" />
                : <div className="flex flex-col items-center gap-1 text-xs text-slate-400"><ImageIcon className="w-6 h-6" />Not generated yet</div>}
          </div>
          {busy && <p className="text-xs text-slate-500 mt-2">Usually takes 5–20 seconds.</p>}
        </div>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
    </Modal>
  );
}

// <img> that shows a grey skeleton until the (often large) file has loaded.
function LoadingImage({ src, className, onError }) {
  const [loadedSrc, setLoadedSrc] = useState('');
  const loaded = loadedSrc === src;
  return (
    <div className="relative w-full h-full">
      {!loaded && <Skeleton className="absolute inset-0 rounded-none" />}
      <img src={src} alt="" className={`${className} ${loaded ? '' : 'opacity-0'}`} onLoad={() => setLoadedSrc(src)} onError={onError} />
    </div>
  );
}

function ImagePicker({ value, onChange, scenarioId, token, onError, aiEnabled, aiRequest, portrait = false }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [broken, setBroken] = useState('');
  const [genOpen, setGenOpen] = useState(false);

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

  const failed = value && broken === value;
  const preview = (
    <div className={`${portrait ? 'w-full h-52' : 'w-full aspect-video'} shrink-0 rounded-xl bg-gray-50 border border-slate-200 overflow-hidden flex items-center justify-center`}>
      {value && !failed
        ? <LoadingImage src={assetUrl(value)} className="w-full h-full object-contain" onError={() => setBroken(value)} />
        : (
          <div className="flex flex-col items-center gap-1 text-xs text-slate-400 text-center px-2">
            <ImageOff className="w-5 h-5" />{failed ? 'Image not found' : 'No image'}
          </div>
        )}
    </div>
  );

  return (
    <div className={portrait ? 'w-full md:w-48 space-y-3' : 'space-y-3'}>
      {genOpen && (
        <ImageGenDialog scenarioId={scenarioId} token={token} request={aiRequest} portrait={portrait}
          onClose={() => setGenOpen(false)} onUse={(url) => { onChange(url); setGenOpen(false); }} />
      )}
      {preview}
      <div className="flex-1 min-w-0 space-y-2">
        <input className={fieldCls} value={value ?? ''} onChange={(e) => onChange(e.target.value)} placeholder="/img4.png or uploaded URL" aria-label="Image URL" />
        <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ''; }} />
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => inputRef.current?.click()} disabled={busy} className={btn.secondary}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {busy ? 'Uploading…' : 'Upload'}
          </button>
          {aiRequest && (
            <button type="button" onClick={() => setGenOpen(true)} disabled={!aiEnabled}
              title={aiEnabled ? 'Draw this image with AI' : 'Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in .env to turn this on'}
              className={`${btn.secondary} bg-amber-50! border-amber-200! text-amber-800! hover:bg-amber-100!`}>
              <Wand2 className="w-4 h-4" /> Generate
            </button>
          )}
        </div>
        <p className="text-xs text-slate-500">PNG, JPG or WEBP, up to 5 MB{aiRequest && !aiEnabled ? '. AI images are off (see .env).' : '.'}</p>
      </div>
    </div>
  );
}

// ───────────────────────────── story tab ─────────────────────────────

let rowSeq = 0;
const toRows = (obj) => Object.entries(obj ?? {}).map(([key, v]) => ({
  id: ++rowSeq, key, kind: typeof v === 'string' ? 'text' : 'json',
  text: typeof v === 'string' ? v : JSON.stringify(v, null, 2),
}));

function rowsToObject(rows) {
  const out = {};
  const errors = {};
  for (const r of rows) {
    const key = r.key.trim();
    if (!key && !r.text.trim()) continue;
    if (!key) { errors[r.id] = 'Give this field a name.'; continue; }
    if (key in out) { errors[r.id] = `"${key}" is used twice.`; continue; }
    if (r.kind === 'json') {
      try { out[key] = JSON.parse(r.text); } catch (e) { errors[r.id] = `Invalid JSON: ${e.message}`; }
    } else out[key] = r.text;
  }
  return { out, errors };
}

// Setting details as name/value fields; nested values (e.g. vehicles) stay as small JSON boxes.
function SettingEditor({ value, onChange, onJsonError }) {
  const [mode, setMode] = useState('fields');
  const [rows, setRows] = useState(() => toRows(value));
  const [errors, setErrors] = useState({});
  const [raw, setRaw] = useState('');
  const [rawError, setRawError] = useState('');

  // Text is re-created from saved data on mount, so it is valid again.
  useEffect(() => { onJsonError(false); }, []);

  const commitRows = (next) => {
    setRows(next);
    const { out, errors: errs } = rowsToObject(next);
    setErrors(errs);
    const bad = Object.keys(errs).length > 0;
    onJsonError(bad);
    if (!bad) onChange(out);
  };
  const setRow = (id, patch) => commitRows(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const changeRaw = (text) => {
    setRaw(text);
    try {
      const parsed = JSON.parse(text || '{}');
      if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) throw new Error('Must be a JSON object');
      setRawError('');
      onJsonError(false);
      onChange(parsed);
    } catch (e) {
      setRawError(e.message);
      onJsonError(true);
    }
  };

  const switchMode = () => {
    if (mode === 'fields') {
      setRaw(JSON.stringify(value ?? {}, null, 2));
      setRawError('');
      setMode('json');
    } else {
      if (rawError) return;
      setRows(toRows(value));
      setErrors({});
      setMode('fields');
    }
  };

  const toggle = (
    <button type="button" onClick={switchMode} disabled={mode === 'json' && !!rawError} className={btn.small}
      title={mode === 'json' && rawError ? 'Fix the JSON first' : ''}>
      {mode === 'fields' ? <><Braces className="w-3.5 h-3.5" /> Edit as JSON</> : <><List className="w-3.5 h-3.5" /> Edit as fields</>}
    </button>
  );

  return (
    <Card title="Setting details" subtitle="Location, time, weather, crowd, vehicles… any fields you like." actions={toggle}>
      {mode === 'json' ? (
        <div>
          <TextArea rows={18} mono value={raw} onChange={changeRaw} aria-label="Setting details JSON" />
          {rawError && <p className="text-xs text-rose-600 mt-1.5">Invalid JSON: {rawError}</p>}
        </div>
      ) : (
        <div className="space-y-3">
          {rows.length === 0 && <p className="text-sm text-slate-500">No setting details yet.</p>}
          {rows.map((r) => (
            <div key={r.id}>
              <div className="grid grid-cols-1 sm:grid-cols-[8.5rem_minmax(0,1fr)_auto] gap-2 items-start">
                <input className={fieldCls} value={r.key} placeholder="Field name" aria-label="Field name"
                  onChange={(e) => setRow(r.id, { key: e.target.value })} />
                <textarea className={`${inputCls} resize-y leading-relaxed field-sizing-content min-h-11 max-h-72 ${r.kind === 'json' ? 'font-mono text-[13px]' : ''}`}
                  rows={r.kind === 'json' ? Math.min(8, r.text.split('\n').length) : Math.min(5, Math.max(1, Math.ceil(r.text.length / 55)))}
                  value={r.text} spellCheck={r.kind === 'text'} aria-label={`${r.key || 'Field'} value`}
                  onChange={(e) => setRow(r.id, { text: e.target.value })} />
                <button type="button" aria-label={`Remove ${r.key || 'field'}`} onClick={() => commitRows(rows.filter((x) => x.id !== r.id))}
                  className="h-11 w-11 inline-flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
              {r.kind === 'json' && !errors[r.id] && <p className="text-xs text-slate-400 mt-1 sm:ml-[9rem]">Nested value (JSON)</p>}
              {errors[r.id] && <p className="text-xs text-rose-600 mt-1 sm:ml-[9rem]">{errors[r.id]}</p>}
            </div>
          ))}
          <button type="button" onClick={() => commitRows([...rows, { id: ++rowSeq, key: '', kind: 'text', text: '' }])}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-800 hover:text-amber-900">
            <Plus className="w-4 h-4" /> Add field
          </button>
        </div>
      )}
    </Card>
  );
}

function StoryTab({ data, update, imageProps, onJsonError }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3 items-start">
        <Card title="Basics" subtitle="How this scenario appears in the player." className="lg:col-span-2">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Title" required htmlFor="sc-title" className="sm:col-span-2">
              <input id="sc-title" className={fieldCls} value={data.title ?? ''} onChange={(e) => update((d) => ({ ...d, title: e.target.value }))} />
            </Field>
            <Field label="Subtitle" htmlFor="sc-subtitle" help="Shown under the title in the player, e.g. the location.">
              <input id="sc-subtitle" className={fieldCls} value={data.subtitle ?? ''} onChange={(e) => update((d) => ({ ...d, subtitle: e.target.value }))} />
            </Field>
            <Field label="Status" htmlFor="sc-status" help="Drafts are hidden from the player until published.">
              <select id="sc-status" className={fieldCls} value={data.status ?? 'published'} onChange={(e) => update((d) => ({ ...d, status: e.target.value }))}>
                <option value="published">Published</option>
                <option value="draft">Draft</option>
              </select>
            </Field>
          </div>
        </Card>
        <Card title="Background image" subtitle="Full-screen scene behind the story.">
          <ImagePicker {...imageProps} value={data.background_image} onChange={(v) => update((d) => ({ ...d, background_image: v }))}
            aiRequest={{ target: 'background', scenario: scenarioForPrompt(data) }} />
        </Card>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Story seed" subtitle="The opening situation. Every agent sees this.">
          <TextArea rows={16} value={data.description} onChange={(v) => update((d) => ({ ...d, description: v }))} aria-label="Story seed" />
        </Card>
        <SettingEditor value={data.setting} onChange={(setting) => update((d) => ({ ...d, setting }))} onJsonError={onJsonError} />
      </div>
    </div>
  );
}

// ───────────────────────────── characters tab ─────────────────────────────

function Avatar({ character, size = 'w-10 h-10' }) {
  const [broken, setBroken] = useState(false);
  const swatch = CHARACTER_COLORS[character.color]?.swatch ?? 'bg-slate-500';
  if (character.image && !broken) {
    return <img src={assetUrl(character.image)} alt="" onError={() => setBroken(true)} className={`${size} rounded-full object-cover bg-gray-100 border border-gray-100 shrink-0`} />;
  }
  return <div className={`${size} rounded-full ${swatch} text-white text-xs font-semibold flex items-center justify-center shrink-0`}>{initials(character.name)}</div>;
}

function AppealsEditor({ appeals, onChange }) {
  const entries = Object.entries(appeals ?? {});
  const setEntry = (idx, name, keywords) => {
    const next = entries.map((e, i) => (i === idx ? [name, keywords] : e));
    onChange(Object.fromEntries(next));
  };
  return (
    <div className="space-y-3">
      {entries.length > 0 && (
        <div className="hidden sm:grid grid-cols-[14rem_1fr_2.75rem] gap-2 text-xs font-medium text-slate-700">
          <span>Appeal</span><span>Keywords (comma separated)</span><span />
        </div>
      )}
      {entries.map(([name, keywords], idx) => (
        <div key={idx} className="grid grid-cols-1 sm:grid-cols-[14rem_1fr_2.75rem] gap-2 items-start">
          <input className={fieldCls} value={name} placeholder="Appeal name" aria-label="Appeal name"
            onChange={(e) => setEntry(idx, e.target.value, keywords)} />
          <input className={fieldCls} value={keywords.join(',')} placeholder="keyword, another keyword" aria-label="Keywords"
            onChange={(e) => setEntry(idx, name, e.target.value.split(','))} />
          <button type="button" aria-label="Remove appeal" onClick={() => onChange(Object.fromEntries(entries.filter((_, i) => i !== idx)))}
            className="h-11 w-11 inline-flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
      <button type="button" onClick={() => onChange({ ...appeals, [`New appeal ${entries.length + 1}`]: [] })}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-800 hover:text-amber-900">
        <Plus className="w-4 h-4" /> Add appeal
      </button>
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
    <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)] items-start">
      <Card padded={false} title="Cast" subtitle={`${chars.length} characters`} className="lg:sticky lg:top-6">
        <ul className="divide-y divide-gray-100">
          {chars.map((ch, i) => (
            <li key={i}>
              <button type="button" onClick={() => setSelected(i)} aria-current={i === idx}
                className={`w-full flex items-center gap-3 px-5 py-3 text-left transition-colors ${i === idx ? 'bg-amber-50 border-r-4 border-amber-700' : 'hover:bg-gray-50'}`}>
                <Avatar character={ch} />
                <div className="min-w-0">
                  <div className={`text-sm font-medium truncate ${i === idx ? 'text-amber-800' : 'text-slate-900'}`}>{ch.name || 'Unnamed'}</div>
                  <div className="text-xs text-slate-500 truncate">{ch.label}</div>
                </div>
              </button>
            </li>
          ))}
        </ul>
        <div className="p-4 border-t border-gray-100">
          <button type="button" onClick={addCharacter} className={`${btn.secondary} w-full`}><Plus className="w-4 h-4" /> Add character</button>
        </div>
      </Card>

      {c && (
        <div className="space-y-6 min-w-0">
          <Card title="Identity" subtitle="Who this character is and how they look in the player.">
            <div className="grid gap-6 md:grid-cols-[12rem_minmax(0,1fr)]">
              <ImagePicker {...imageProps} portrait value={c.image} onChange={(v) => setChar({ image: v })}
                aiRequest={{ target: 'character', scenario: scenarioForPrompt(data), character: { name: c.name, label: c.label, description: c.description } }} />
              <div className="grid gap-5 sm:grid-cols-2 content-start">
                <Field label="Name" required htmlFor="ch-name" help="Used in prompts and by the Director.">
                  <input id="ch-name" className={fieldCls} value={c.name} onChange={(e) => setChar({ name: e.target.value })} />
                </Field>
                <Field label="Display label" htmlFor="ch-label" help="Shown on the character card.">
                  <input id="ch-label" className={fieldCls} value={c.label} onChange={(e) => setChar({ label: e.target.value })} />
                </Field>
                <Field label="Key" htmlFor="ch-key" help="Internal id (letters, numbers, _).">
                  <input id="ch-key" className={`${fieldCls} font-mono`} value={c.key} onChange={(e) => setChar({ key: slugify(e.target.value) })} />
                </Field>
                <Field label="Colour">
                  <div className="flex flex-wrap gap-2 pt-1.5">
                    {(meta?.colors ?? Object.keys(CHARACTER_COLORS)).map((col) => (
                      <button key={col} type="button" aria-label={col} title={col} aria-pressed={c.color === col} onClick={() => setChar({ color: col })}
                        className={`w-8 h-8 rounded-full ${CHARACTER_COLORS[col]?.swatch ?? 'bg-slate-500'} ${c.color === col ? 'ring-2 ring-offset-2 ring-slate-900' : ''}`} />
                    ))}
                  </div>
                </Field>
              </div>
            </div>
          </Card>

          <Card title="Role in the story" subtitle="Seen by the Director and Reviewer.">
            <div className="space-y-5">
              <Field label="Short description">
                <TextArea rows={4} value={c.description} onChange={(v) => setChar({ description: v })} />
              </Field>
              <div className="grid gap-5 md:grid-cols-2">
                <Field label="Goals" help="One per line.">
                  <TextArea rows={5} value={(c.goals ?? []).join('\n')} onChange={(v) => setChar({ goals: v.split('\n') })} />
                </Field>
                <Field label="Inventory" help="One item per line.">
                  <TextArea rows={5} value={(c.inventory ?? []).join('\n')} onChange={(v) => setChar({ inventory: v.split('\n') })} />
                </Field>
              </div>
            </div>
          </Card>

          <Card title="Persona" subtitle="The heart of the character: psychology, language, tactics per turn, flaws, how they address others.">
            <div className="space-y-5">
              <Field label="Persona (deep instructions)" help="Goes into {persona}.">
                <TextArea rows={18} mono value={c.persona} onChange={(v) => setChar({ persona: v })} />
              </Field>
              <Field label="English-mode style" help="How this character speaks when the story runs in English. Goes into {english_style}.">
                <TextArea rows={5} mono value={c.english_style} onChange={(v) => setChar({ english_style: v })} />
              </Field>
            </div>
          </Card>

          <Card title="Reviewer notes" subtitle="What the Reviewer checks for this character.">
            <div className="grid gap-5 md:grid-cols-2">
              <Field label="Roman Urdu">
                <TextArea rows={4} value={c.review_notes_urdu} onChange={(v) => setChar({ review_notes_urdu: v })} />
              </Field>
              <Field label="English">
                <TextArea rows={4} value={c.review_notes_english} onChange={(v) => setChar({ review_notes_english: v })} />
              </Field>
            </div>
          </Card>

          <Card title="Repeated appeals" subtitle="Keywords that detect a repeated tactic. The more it's used, the more the character is told the crowd is tired of it.">
            <AppealsEditor appeals={c.appeals} onChange={(appeals) => setChar({ appeals })} />
          </Card>

          <Card title="Voice" subtitle="Text-to-speech voice used by the player.">
            <div className="grid gap-5 md:grid-cols-3">
              <Field label="TTS voice" htmlFor="ch-voice">
                <select id="ch-voice" className={fieldCls} value={c.voice?.voice ?? ''} onChange={(e) => setChar({ voice: { ...c.voice, voice: e.target.value } })}>
                  {[...new Set([c.voice?.voice, ...(meta?.voices ?? [])].filter(Boolean))].map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </Field>
              <Field label="Speed" htmlFor="ch-rate" help="e.g. +15% or -10%">
                <input id="ch-rate" className={fieldCls} value={c.voice?.rate ?? ''} onChange={(e) => setChar({ voice: { ...c.voice, rate: e.target.value } })} />
              </Field>
              <Field label="Pitch" htmlFor="ch-pitch" help="e.g. +6Hz or -4Hz">
                <input id="ch-pitch" className={fieldCls} value={c.voice?.pitch ?? ''} onChange={(e) => setChar({ voice: { ...c.voice, pitch: e.target.value } })} />
              </Field>
            </div>
          </Card>

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={removeCharacter} disabled={chars.length <= 2} className={btn.danger}>
              <Trash2 className="w-4 h-4" /> Remove {c.name || 'character'}
            </button>
            {chars.length <= 2 && <span className="text-xs text-slate-500">A story needs at least 2 characters.</span>}
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────── prompts tab ─────────────────────────────

function PromptsTab({ data, update, meta }) {
  const names = Object.keys(meta?.prompts ?? PROMPT_INFO);
  const [selected, setSelected] = useState(names[0]);
  const textRef = useRef(null);
  const spec = meta?.prompts?.[selected] ?? { allowed: [], required: [] };
  const value = data.prompts?.[selected] ?? '';
  const isTemplate = selected !== 'fallback_conclusion';
  const { unknown, missing } = promptProblems(selected, value, meta?.prompts?.[selected]);
  const info = PROMPT_INFO[selected];

  const setValue = (v) => update((d) => ({ ...d, prompts: { ...d.prompts, [selected]: v } }));

  const insert = (name) => {
    const el = textRef.current;
    const token = `{${name}}`;
    if (!el) return setValue(value + token);
    const { selectionStart: a, selectionEnd: b } = el;
    setValue(value.slice(0, a) + token + value.slice(b));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(a + token.length, a + token.length); });
  };

  const groups = PROMPT_GROUPS.map((g) => [g, names.filter((n) => (PROMPT_INFO[n]?.group ?? 'Other') === g)]).filter(([, list]) => list.length);

  return (
    <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)] items-start">
      <Card padded={false} title="Prompts" subtitle="Templates each agent receives." className="lg:sticky lg:top-6">
        <nav className="py-2">
          {groups.map(([group, list]) => (
            <div key={group} className="py-1">
              <div className="px-5 pt-2 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{group}</div>
              {list.map((n) => {
                const p = promptProblems(n, data.prompts?.[n], meta?.prompts?.[n]);
                const bad = p.unknown.length + p.missing.length > 0;
                return (
                  <button key={n} type="button" onClick={() => setSelected(n)} aria-current={n === selected}
                    className={`w-full flex items-center justify-between gap-2 px-5 py-2 text-sm text-left transition-colors ${n === selected ? 'bg-amber-50 text-amber-800 font-medium border-r-4 border-amber-700' : 'text-slate-600 hover:bg-gray-50 hover:text-slate-900'}`}>
                    <span className="truncate">{PROMPT_INFO[n]?.label ?? n}</span>
                    {bad && <span className="w-2 h-2 rounded-full bg-rose-500 shrink-0" title="Placeholder problem" />}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </Card>

      <Card title={info ? `${info.group === 'Other' ? '' : `${info.group} · `}${info.label}` : selected} subtitle={info?.help}>
        <div className="space-y-4">
          {isTemplate && (
            <div className="rounded-xl bg-gray-50 border border-slate-200 p-3.5 space-y-2.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-medium text-slate-700 mr-1">Placeholders (click to insert):</span>
                {spec.allowed.map((p) => (
                  <button key={p} type="button" onClick={() => insert(p)}
                    className={`font-mono text-xs px-2 py-1 rounded-md border transition-colors ${spec.required.includes(p) ? 'border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-100'}`}>
                    {`{${p}}`}{spec.required.includes(p) && ' *'}
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-500">* required. For literal braces in JSON examples write <code className="font-mono text-slate-700">{'{{'}</code> and <code className="font-mono text-slate-700">{'}}'}</code>.</p>
            </div>
          )}
          {(unknown.length > 0 || missing.length > 0) && (
            <Notice tone="error">
              {unknown.length > 0 && <div>Unknown placeholder(s): {unknown.map((u) => `{${u}}`).join(', ')}</div>}
              {missing.length > 0 && <div>Missing required: {missing.map((u) => `{${u}}`).join(', ')}</div>}
            </Notice>
          )}
          <textarea ref={textRef} value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false} aria-label="Prompt text"
            rows={isTemplate ? 30 : 6} className={`${inputCls} font-mono text-[13px] leading-relaxed resize-y`} />
          <p className="text-xs text-slate-400 text-right">{value.length.toLocaleString()} characters</p>
        </div>
      </Card>
    </div>
  );
}

// ───────────────────────────── settings tab ─────────────────────────────

function SettingsTab({ data, update, meta }) {
  const settings = data.settings ?? {};
  const set = (key, v) => update((d) => ({ ...d, settings: { ...d.settings, [key]: v === '' ? '' : Number(v) } }));
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        {SETTINGS_GROUPS.map(([title, subtitle, fields]) => (
          <Card key={title} title={title} subtitle={subtitle}>
            <div className="space-y-5">
              {fields.map(([key, label, help]) => (
                <Field key={key} label={label} htmlFor={`set-${key}`}
                  help={`${help}${meta?.default_settings?.[key] !== undefined ? ` Default: ${meta.default_settings[key]}.` : ''}`}>
                  <input id={`set-${key}`} type="number" step={key === 'temperature' ? 0.05 : 1} min={0} max={key === 'temperature' ? 2 : undefined}
                    className={fieldCls} value={settings[key] ?? ''} onChange={(e) => set(key, e.target.value)} />
                </Field>
              ))}
            </div>
          </Card>
        ))}
      </div>
      <p className="text-xs text-slate-500">The LLM models and API keys stay in the server's <code className="font-mono text-slate-700">.env</code> (GEMINI_MODEL, GEMINI_FALLBACK_MODELS, OPENAI_MODEL).</p>
    </div>
  );
}

// ───────────────────────────── history tab ─────────────────────────────

function HistoryTab({ token, scenarioId, currentVersion, dirty, onRestored, onError }) {
  const [versions, setVersions] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setVersions(null);
    setPreview(null);
    api(`/api/admin/scenarios/${scenarioId}/versions`, { token }).then((r) => setVersions(r.versions)).catch((e) => onError(e.message));
  }, [token, scenarioId, currentVersion]);

  const show = async (v) => {
    try { setPreview(await api(`/api/admin/scenarios/${scenarioId}/versions/${v}`, { token }).then((d) => ({ ...d, _v: v }))); }
    catch (e) { onError(e.message); }
  };
  const restore = async (v) => {
    if (dirty && !window.confirm('You have unsaved changes. Restoring will discard them. Continue?')) return;
    if (!window.confirm(`Restore version ${v}? It becomes a new version, so nothing is lost.`)) return;
    setBusy(true);
    try { onRestored(await api(`/api/admin/scenarios/${scenarioId}/versions/${v}/restore`, { token, method: 'POST' }), v); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  };

  if (!versions) {
    return (
      <div className="grid gap-6 xl:grid-cols-2 items-start">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden"><SkeletonRows rows={5} cols={4} /></div>
        <SkeletonCard fields={1} tall />
      </div>
    );
  }
  return (
    <div className="grid gap-6 xl:grid-cols-2 items-start">
      <Card padded={false} title="Versions" subtitle="Every save stores a full copy of the scenario. Restore any version at any time.">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                {['Version', 'Note', 'Saved', ''].map((h) => (
                  <th key={h} className="px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wide text-left whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {versions.map((v) => (
                <tr key={v.version} className={preview?._v === v.version ? 'bg-amber-50/60' : 'hover:bg-gray-50'}>
                  <td className="px-5 py-4 text-sm font-semibold text-slate-900 whitespace-nowrap">
                    v{v.version} {v.version === currentVersion && <span className="ml-1"><Badge tone="green">Current</Badge></span>}
                  </td>
                  <td className="px-5 py-4 text-sm text-slate-600">{v.note}</td>
                  <td className="px-5 py-4 text-sm text-slate-500 whitespace-nowrap" title={formatDate(v.created_at)}>{timeAgo(v.created_at)}</td>
                  <td className="px-5 py-4 text-right whitespace-nowrap">
                    <div className="inline-flex gap-2">
                      <button type="button" onClick={() => show(v.version)} className={btn.small}>View</button>
                      {v.version !== currentVersion && (
                        <button type="button" disabled={busy} onClick={() => restore(v.version)} className={btn.small}>Restore</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title={preview ? `Version ${preview._v}: ${preview.title}` : 'Preview'}
        subtitle={preview ? `${preview.status} · ${preview.characters?.length} characters: ${preview.characters?.map((c) => c.name).join(', ')}` : 'Select “View” on a version to see what it contained.'}>
        {preview
          ? <pre className="text-xs bg-gray-50 border border-slate-200 rounded-xl p-3.5 max-h-[65vh] overflow-auto whitespace-pre-wrap text-slate-700">{JSON.stringify(preview, (k, v) => (k === '_v' ? undefined : v), 2)}</pre>
          : <p className="text-sm text-slate-500">Nothing selected.</p>}
      </Card>
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
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4" style={{ fontFamily: FONT }}>
      <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-2xl border border-gray-100 shadow-sm p-8 space-y-6">
        <div>
          <h1 className="text-2xl! leading-tight! font-bold text-gray-900 tracking-tight">Narrative Admin</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to edit stories, characters and prompts.</p>
        </div>
        <Field label="Password" required htmlFor="admin-password">
          <input id="admin-password" type="password" autoFocus className={fieldCls} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <button type="submit" disabled={busy || !password} className={`${btn.primary} w-full`}>
          {busy ? <><Loader2 className="w-4 h-4 animate-spin" /> Signing in…</> : 'Sign in'}
        </button>
        <a href="/" className="block text-center text-sm text-slate-500! hover:text-slate-800!">Back to the story player</a>
      </form>
    </div>
  );
}

// ───────────────────────────── dialogs ─────────────────────────────

const EXAMPLE_BRIEFS = [
  'Lahore ki shaadi mein khana waqt se pehle khatam ho gaya — dulhe ka baap, caterer, dulhan ki phuppo aur photographer aamne saamne.',
  'Karachi ke ek flat ki building mein lift phans gayi: landlord, ek naya kirayedar, chowkidar aur ek aunty jo sab jaanti hai.',
  'Islamabad ke petrol pump pe line torne pe jhagra: ek fauji retired colonel, ek food-delivery rider, pump manager aur ek TikToker.',
];

function GenerateDialog({ token, aiImages, onClose, onCreated }) {
  const [brief, setBrief] = useState('');
  const [count, setCount] = useState(4);
  const [withImages, setWithImages] = useState(aiImages);
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
        body: JSON.stringify({ brief, num_characters: count, images: withImages }),
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
    <Modal size="max-w-2xl" title="New scenario with AI" onClose={onClose} closeDisabled={running}
      subtitle={`Describe the scene in a line or two. The AI writes the story seed, setting, characters with deep personas, and adapts every prompt.${withImages ? ' It can also draw every character and the background.' : ' You add images afterwards.'}`}
      footer={(
        <>
          <button type="button" onClick={() => (running ? abortRef.current?.abort() : onClose())} className={btn.secondary}>{running ? 'Stop' : 'Cancel'}</button>
          <button type="button" onClick={run} disabled={running || brief.trim().length < 10} className={btn.primary}>
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} {running ? 'Generating…' : 'Generate'}
          </button>
        </>
      )}>
      <Field label="Scene idea" required htmlFor="gen-brief" help="Roman Urdu or English. Mention who is there and what just happened.">
        <TextArea id="gen-brief" rows={4} value={brief} onChange={setBrief} disabled={running}
          placeholder="e.g. Karachi ke ek flat ki building mein lift phans gayi…" />
      </Field>
      <div>
        <div className="text-xs font-medium text-slate-700 mb-1.5">Examples</div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_BRIEFS.map((b) => (
            <button key={b} type="button" disabled={running} onClick={() => setBrief(b)}
              className="text-left text-xs px-3 py-1.5 rounded-lg bg-gray-50 border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors disabled:opacity-40">
              {b.length > 70 ? `${b.slice(0, 70)}…` : b}
            </button>
          ))}
        </div>
      </div>
      <Field label="Number of characters" htmlFor="gen-count" className="w-32">
        <select id="gen-count" className={fieldCls} value={count} disabled={running} onChange={(e) => setCount(Number(e.target.value))}>
          {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </Field>
      <label className={`flex items-start gap-3 rounded-xl border p-3.5 ${aiImages ? 'border-slate-200 cursor-pointer' : 'border-slate-200 bg-gray-50 opacity-70'}`}>
        <input type="checkbox" className="mt-0.5 accent-amber-700" checked={withImages} disabled={!aiImages || running}
          onChange={(e) => setWithImages(e.target.checked)} />
        <span>
          <span className="block text-sm font-medium text-slate-800 flex items-center gap-1.5"><Wand2 className="w-4 h-4 text-amber-700" /> Also draw the images</span>
          <span className="block text-xs text-slate-500 mt-0.5">
            {aiImages
              ? 'A portrait for every character and the scene background, made with an open-source image model (FLUX.1 schnell on Cloudflare, free daily limit).'
              : 'Off: set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in .env and restart the API to turn this on.'}
          </span>
        </span>
      </label>

      {(log.length > 0 || running) && (
        <div className="rounded-xl bg-gray-50 border border-slate-200 p-3.5 space-y-2 text-sm" aria-live="polite">
          {log.map((line, i) => (
            <div key={i} className="flex items-start gap-2 text-slate-700">
              <CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" /> {line}
            </div>
          ))}
          {running && <div className="flex items-center gap-2 text-amber-800"><Loader2 className="w-4 h-4 animate-spin" /> Working… this usually takes 1–4 minutes{withImages ? ', plus about a minute for images' : ''}.</div>}
        </div>
      )}
      {error && <Notice tone="error">{error}</Notice>}
    </Modal>
  );
}

function NewScenarioDialog({ scenarios, defaultSource, onClose, onCreate }) {
  const [title, setTitle] = useState('');
  const [source, setSource] = useState(defaultSource ?? scenarios[0]?.id ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const id = slugify(title);

  const submit = async (e) => {
    e.preventDefault();
    if (!id) return setError('Title needs at least one letter or number.');
    setBusy(true);
    setError('');
    try { await onCreate({ id, title: title.trim(), copy_from: source }); }
    catch (err) { setError(err.message); setBusy(false); }
  };

  return (
    <Modal title="New scenario" subtitle="It starts as a copy of an existing scenario. Edit it and press Save." onClose={onClose} closeDisabled={busy}
      footer={(
        <>
          <button type="button" onClick={onClose} disabled={busy} className={btn.secondary}>Cancel</button>
          <button type="submit" form="new-scenario-form" disabled={busy || !id} className={btn.primary}>
            {busy ? <><Loader2 className="w-4 h-4 animate-spin" /> Creating…</> : <><Plus className="w-4 h-4" /> Create scenario</>}
          </button>
        </>
      )}>
      <form id="new-scenario-form" onSubmit={submit} className="space-y-5">
        <Field label="Title" required htmlFor="new-title">
          <input id="new-title" autoFocus className={fieldCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. The Wedding Buffet" />
          <p className="text-xs text-slate-400 mt-1.5">ID: <span className="font-mono">{id || '—'}</span></p>
        </Field>
        <Field label="Copy from" htmlFor="new-source">
          <select id="new-source" className={fieldCls} value={source} onChange={(e) => setSource(e.target.value)}>
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.title}{s.status === 'draft' ? ' (draft)' : ''}</option>)}
          </select>
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Modal>
  );
}

// Shown while a scenario loads: same shape as the page (header, tabs, Story cards).
function ScenarioSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading scenario">
      <SkeletonHeader />
      <div className="flex gap-6 border-b border-gray-200 pb-3">
        {['w-16', 'w-28', 'w-20', 'w-20', 'w-16'].map((w, i) => <Skeleton key={i} className={`h-4 ${w}`} />)}
      </div>
      <div className="grid gap-6 lg:grid-cols-3 items-start">
        <SkeletonCard fields={3} className="lg:col-span-2" />
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 space-y-3" aria-hidden="true">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="w-full aspect-video" />
          <Skeleton className="h-11 w-full" />
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <SkeletonCard fields={1} tall />
        <SkeletonCard fields={4} />
      </div>
    </div>
  );
}

// ───────────────────────────── sidebar ─────────────────────────────

const navItemCls = (active) => `w-full flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition-colors ${active
  ? 'bg-amber-50 text-amber-800 border-r-4 border-amber-700'
  : 'text-slate-600 hover:bg-gray-50 hover:text-slate-900'}`;

function Sidebar({ open, onClose, view, onView, scenarios, loading, scenarioId, onPick, dbOnline, onNew, onGenerate, onImport, onPlayer, onLogout }) {
  const [query, setQuery] = useState('');
  const shown = scenarios.filter((s) => s.title.toLowerCase().includes(query.trim().toLowerCase()));
  const hideScroll = '[scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden';

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-gray-900/40 backdrop-blur-sm lg:hidden" onClick={onClose} aria-hidden="true" />}
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-white border-r border-gray-200 flex flex-col transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}
        aria-label="Admin navigation">
        <div className="h-16 shrink-0 px-5 flex items-center justify-between border-b border-gray-100">
          <div>
            <div className="text-base font-bold text-slate-900 leading-tight">Narrative Admin</div>
            <div className="text-xs text-slate-400">AI story engine</div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close menu" className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>

        <nav className="py-3 shrink-0">
          <button type="button" onClick={() => onView('scenarios')} className={navItemCls(view === 'scenarios')} aria-current={view === 'scenarios'}>
            <BookOpen className="w-[18px] h-[18px]" /> Scenarios
          </button>
          <button type="button" onClick={() => onView('stories')} className={navItemCls(view === 'stories')} aria-current={view === 'stories'}>
            <Library className="w-[18px] h-[18px]" /> Stories
          </button>
        </nav>

        <div className="px-5 pt-4 pb-3 border-t border-gray-100 shrink-0 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">All scenarios</span>
            <span className="text-xs text-slate-400">{loading ? '' : scenarios.length}</span>
          </div>
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" aria-label="Search scenarios"
              className={`${inputCls} h-9 py-1.5 pl-9`} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" onClick={onNew} disabled={!dbOnline} className={btn.small}><Plus className="w-3.5 h-3.5" /> New</button>
            <button type="button" onClick={onGenerate} disabled={!dbOnline}
              className={`${btn.small} bg-amber-50! border-amber-200! text-amber-800! hover:bg-amber-100!`}><Sparkles className="w-3.5 h-3.5" /> With AI</button>
          </div>
        </div>

        <ul className={`flex-1 overflow-y-auto pb-2 ${hideScroll}`}>
          {shown.map((s) => {
            const active = view === 'scenarios' && s.id === scenarioId;
            return (
              <li key={s.id}>
                <button type="button" onClick={() => onPick(s.id)} aria-current={active}
                  className={`w-full flex items-center gap-2.5 px-5 py-2 text-sm text-left transition-colors ${active ? 'bg-amber-50 text-amber-800 font-medium border-r-4 border-amber-700' : 'text-slate-600 hover:bg-gray-50 hover:text-slate-900'}`}>
                  <span className={`w-2 h-2 rounded-full shrink-0 ${s.status === 'draft' ? 'bg-slate-300' : 'bg-emerald-500'}`}
                    title={s.status === 'draft' ? 'Draft' : 'Published'} />
                  <span className="truncate flex-1">{s.title}</span>
                  {s.status === 'draft' && <span className="text-[11px] text-slate-400">Draft</span>}
                </button>
              </li>
            );
          })}
          {loading && [72, 56, 64, 48, 60].map((w, i) => (
            <li key={i} className="px-5 py-2.5 flex items-center gap-2.5" aria-hidden="true">
              <Skeleton className="w-2 h-2 rounded-full" /><span className="h-3.5 rounded-lg bg-slate-200/70 animate-pulse" style={{ width: `${w}%` }} />
            </li>
          ))}
          {!loading && shown.length === 0 && <li className="px-5 py-3 text-sm text-slate-400">No scenarios match.</li>}
        </ul>

        <div className="mt-auto shrink-0 border-t border-gray-100 py-2">
          <button type="button" onClick={onImport} disabled={!dbOnline} className={`${navItemCls(false)} disabled:opacity-40 disabled:cursor-not-allowed`}>
            <FileUp className="w-[18px] h-[18px]" /> Import scenario
          </button>
          <a href="/" onClick={onPlayer} className={`${navItemCls(false)} text-slate-600!`}>
            <Play className="w-[18px] h-[18px]" /> Open player
          </a>
          <button type="button" onClick={onLogout} className={navItemCls(false)}>
            <LogOut className="w-[18px] h-[18px]" /> Sign out
          </button>
        </div>
      </aside>
    </>
  );
}

// ───────────────────────────── main ─────────────────────────────

const TABS = [
  ['story', 'Story', BookOpen],
  ['characters', 'Characters', Users],
  ['prompts', 'Prompts', MessageSquareCode],
  ['settings', 'Settings', SlidersHorizontal],
  ['history', 'History', History],
];

export default function AdminApp() {
  useAdminFont();
  const [token, setToken] = useState(readToken);
  const [meta, setMeta] = useState(null);
  const [view, setView] = useState('scenarios'); // 'scenarios' | 'stories'
  const [scenarios, setScenarios] = useState([]);
  const [listLoaded, setListLoaded] = useState(false);
  const [scenarioId, setScenarioId] = useState(null);
  const [data, setData] = useState(null);
  const [savedJson, setSavedJson] = useState('');
  const [tab, setTab] = useState('story');
  const [status, setStatus] = useState(null); // {type: 'ok'|'error', text}
  const [saving, setSaving] = useState(false);
  const [jsonError, setJsonError] = useState(false);
  const [dialog, setDialog] = useState(null); // 'generate' | 'new' | null
  const [menuOpen, setMenuOpen] = useState(false);
  const importRef = useRef(null);

  const dirty = data !== null && JSON.stringify(data) !== savedJson;
  const dbOnline = meta?.database !== false;

  const logout = () => { writeToken(''); setToken(''); };
  const handleError = (e) => {
    if (e.status === 401) logout();
    setStatus({ type: 'error', text: e.message });
  };

  const loadList = async () => {
    const res = await api('/api/admin/scenarios', { token });
    setScenarios(res.scenarios ?? []);
    setListLoaded(true);
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

  // Ctrl/Cmd+S saves.
  const saveRef = useRef(null);
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveRef.current?.(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const aiImages = !!meta?.image_generation?.enabled;
  const imageProps = useMemo(() => ({
    scenarioId, token, aiEnabled: aiImages, onError: (msg) => setStatus({ type: 'error', text: msg }),
  }), [scenarioId, token, aiImages]);

  if (!token) return <Login onLogin={(t) => { writeToken(t); setToken(t); setStatus(null); }} />;

  const confirmDiscard = () => !dirty || window.confirm('You have unsaved changes. Discard them?');
  const canSave = view === 'scenarios' && dirty && !saving && !jsonError && dbOnline;

  const pickScenario = (id) => {
    setMenuOpen(false);
    if (id === scenarioId) { setView('scenarios'); return; }
    if (!confirmDiscard()) return;
    setData(null);
    setStatus(null);
    setScenarioId(id);
    setView('scenarios');
  };

  const changeView = (key) => {
    setMenuOpen(false);
    if (key === view) return;
    if (key === 'stories' || confirmDiscard()) setView(key);
  };

  const applySaved = (res) => {
    setData(res);
    setSavedJson(JSON.stringify(res));
  };

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setStatus(null);
    try {
      applySaved(await api(`/api/admin/scenarios/${scenarioId}`, { token, method: 'PUT', body: normalizeForSave(data) }));
      await loadList();
      setStatus({ type: 'ok', text: 'Saved to the database. The next story run uses these changes.' });
    } catch (e) { handleError(e); } finally { setSaving(false); }
  };
  saveRef.current = save;

  const openScenario = async (id, message) => {
    await loadList();
    setData(null);
    setScenarioId(id);
    setTab('story');
    setView('scenarios');
    if (message) setStatus({ type: 'ok', text: message });
  };

  const createScenario = async ({ id, title, copy_from }) => {
    await api('/api/admin/scenarios', { token, method: 'POST', body: { id, title, copy_from } });
    setDialog(null);
    await openScenario(id, `Created “${title}”. Edit it and press Save.`);
  };

  const onGenerated = async (event) => {
    setDialog(null);
    await openScenario(event.id);
    const extra = event.warnings?.length ? ` Note: ${event.warnings.join(' ')}` : '';
    setStatus({ type: event.warnings?.length ? 'error' : 'ok',
      text: `Draft “${event.title}” created. Review it, add images, set Status to Published and Save.${extra}` });
  };

  const deleteScenario = async () => {
    if (!window.confirm(`Delete "${data?.title}" permanently? Its history and unused images are deleted too (its story runs are kept). This cannot be undone.`)) return;
    try {
      await api(`/api/admin/scenarios/${scenarioId}`, { token, method: 'DELETE' });
      const res = await loadList();
      setData(null);
      setSavedJson('');
      setScenarioId(res.default ?? res.scenarios?.[0]?.id ?? null);
      setStatus({ type: 'ok', text: 'Scenario deleted.' });
    } catch (e) { handleError(e); }
  };

  const exportScenario = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/scenarios/${scenarioId}/export`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Export failed (${res.status})`);
      downloadJson(`${scenarioId}.scenario.json`, await res.text());
    } catch (e) { handleError(e); }
  };

  const importScenario = async (file) => {
    if (!file || !confirmDiscard()) return;
    try {
      const payload = JSON.parse(await file.text());
      const res = await api('/api/admin/scenarios/import', { token, method: 'POST', body: payload });
      await openScenario(res.id, `Imported “${res.title}” as a new scenario.`);
    } catch (e) { handleError(e instanceof SyntaxError ? new Error('That file is not valid JSON.') : e); }
  };

  const update = (fn) => setData((d) => fn(d));
  const isDefault = scenarioId === 'rickshaw_accident';

  return (
    <div className="min-h-screen bg-gray-50 text-slate-900" style={{ fontFamily: FONT }}>
      {dialog === 'generate' && <GenerateDialog token={token} aiImages={aiImages} onClose={() => setDialog(null)} onCreated={onGenerated} />}
      {dialog === 'new' && <NewScenarioDialog scenarios={scenarios} defaultSource={scenarioId} onClose={() => setDialog(null)} onCreate={createScenario} />}
      <input ref={importRef} type="file" accept=".json,application/json" className="hidden"
        onChange={(e) => { importScenario(e.target.files?.[0]); e.target.value = ''; }} />

      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} view={view} onView={changeView}
        scenarios={scenarios} loading={!listLoaded} scenarioId={scenarioId} onPick={pickScenario} dbOnline={dbOnline}
        onNew={() => { setMenuOpen(false); if (confirmDiscard()) setDialog('new'); }}
        onGenerate={() => { setMenuOpen(false); if (confirmDiscard()) setDialog('generate'); }}
        onImport={() => { setMenuOpen(false); importRef.current?.click(); }}
        onPlayer={(e) => { if (!confirmDiscard()) e.preventDefault(); }}
        onLogout={() => confirmDiscard() && logout()} />

      <div className="lg:pl-64">
        {/* Small screens only: the one exception to "no top bar". */}
        <div className="lg:hidden sticky top-0 z-20 h-14 bg-white border-b border-gray-200 flex items-center gap-3 px-4">
          <button type="button" onClick={() => setMenuOpen(true)} aria-label="Open menu" className="p-2 -ml-2 rounded-lg text-slate-600 hover:bg-slate-100"><Menu className="w-5 h-5" /></button>
          <span className="font-bold text-slate-900">Narrative Admin</span>
        </div>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8 space-y-6">
          {!dbOnline && (
            <Notice tone="warn">
              The database is not connected, so the panel is <b>read-only</b>: scenarios come from the backup files and nothing can be saved. Story runs aren't recorded. Check <code>DATABASE_URL</code> and restart the API.
            </Notice>
          )}

          {view === 'stories' ? (
            <>
              {status && <Notice tone={status.type} onDismiss={() => setStatus(null)}>{status.text}</Notice>}
              {dbOnline
                ? <RunsView token={token} scenarios={scenarios} onError={(msg) => setStatus({ type: 'error', text: msg })} />
                : <Card><p className="text-sm text-slate-500">Story runs are stored in the database, which is not connected.</p></Card>}
            </>
          ) : !data ? (
            status?.type === 'error'
              ? <Notice tone="error" onDismiss={() => setStatus(null)}>{status.text}</Notice>
              : <ScenarioSkeleton />
          ) : (
            <>
              <header className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h1 className="text-2xl! leading-tight! font-bold text-gray-900 tracking-tight">{data.title || 'Untitled scenario'}</h1>
                    {data.status === 'draft' ? <Badge tone="gray">Draft</Badge> : <Badge tone="green">Published</Badge>}
                  </div>
                  <p className="text-sm text-gray-500 mt-1">
                    {[data.subtitle, `${data.characters.length} characters`, data.version && `v${data.version}`,
                      data.updated_at && `saved ${timeAgo(data.updated_at)}`].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {dirty && <span className="hidden sm:inline text-xs font-medium text-amber-800">Unsaved changes</span>}
                  <button type="button" onClick={save} disabled={!canSave} className={btn.primary}
                    title={jsonError ? 'Fix the setting details first' : dirty ? 'Save (Ctrl+S)' : ''}>
                    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
                  </button>
                  <MoreMenu items={[
                    { label: 'Export scenario', icon: Download, onClick: exportScenario, disabled: !dbOnline, title: 'Download this scenario with its images' },
                    { divider: true },
                    { label: 'Delete scenario', icon: Trash2, onClick: deleteScenario, danger: true, disabled: isDefault || !dbOnline,
                      title: isDefault ? 'The default scenario cannot be deleted' : '' },
                  ]} />
                </div>
              </header>

              <nav className={`flex gap-6 border-b border-gray-200 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden`} aria-label="Scenario sections">
                {TABS.map(([key, label, Icon]) => (
                  <button key={key} type="button" onClick={() => setTab(key)} aria-current={tab === key}
                    className={`inline-flex items-center gap-2 pb-3 -mb-px border-b-2 text-sm font-medium whitespace-nowrap transition-colors ${tab === key ? 'border-amber-700 text-amber-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                    <Icon className="w-4 h-4" /> {label}
                    {key === 'characters' && <span className="text-xs text-slate-400 font-normal">{data.characters.length}</span>}
                  </button>
                ))}
              </nav>

              {status && <Notice tone={status.type} onDismiss={() => setStatus(null)}>{status.text}</Notice>}
              {jsonError && tab === 'story' && (
                <Notice tone="error">Setting details have a problem (see below). Fix it to enable Save.</Notice>
              )}

              <div key={scenarioId}>
                {tab === 'story' && <StoryTab data={data} update={update} imageProps={imageProps} onJsonError={setJsonError} />}
                {tab === 'characters' && <CharactersTab data={data} update={update} meta={meta} imageProps={imageProps} />}
                {tab === 'prompts' && <PromptsTab data={data} update={update} meta={meta} />}
                {tab === 'settings' && <SettingsTab data={data} update={update} meta={meta} />}
                {tab === 'history' && (dbOnline
                  ? <HistoryTab token={token} scenarioId={scenarioId} currentVersion={data.version} dirty={dirty}
                      onError={(msg) => setStatus({ type: 'error', text: msg })}
                      onRestored={(res, v) => { applySaved(res); loadList(); setStatus({ type: 'ok', text: `Restored version ${v} (saved as v${res.version}).` }); }} />
                  : <Card><p className="text-sm text-slate-500">History is stored in the database, which is not connected.</p></Card>)}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
