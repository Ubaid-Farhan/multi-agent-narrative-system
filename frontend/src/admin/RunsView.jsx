import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  RefreshCw, Loader2, Trash2, Download, Brain, ChevronDown, ChevronRight, AlertTriangle,
  Clapperboard, Sparkles, MessageSquare, ShieldCheck, ShieldX, Hand, Flag, Globe2, Scale, Ban, Cpu, Repeat,
} from 'lucide-react';
import { api, inputCls, downloadJson, formatDate, timeAgo } from './common';

const STATUS_STYLES = {
  completed: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  incomplete: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  failed: 'bg-red-500/15 text-red-300 border-red-500/30',
  aborted: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
  running: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
};
const STATUS_HELP = {
  completed: 'Finished with an ending and no failed turns — used for offline replay',
  incomplete: 'Finished, but some turns failed or there was no ending',
  failed: 'Stopped because of an error',
  aborted: 'The viewer left, or the server restarted, before it finished',
  running: 'Still being generated',
};
const PAGE_SIZE = 30;

function StatusBadge({ status }) {
  return (
    <span title={STATUS_HELP[status]} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold uppercase tracking-wide ${STATUS_STYLES[status] ?? STATUS_STYLES.aborted}`}>
      {status === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}{status}
    </span>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="text-sm text-gray-100 mt-0.5 break-words">{value ?? '—'}</div>
    </div>
  );
}

function Collapsible({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button type="button" onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200">
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />} {label}
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

function Json({ value }) {
  return <pre className="text-xs bg-black/40 border border-white/10 rounded-lg p-2 overflow-x-auto max-h-64 text-gray-300 whitespace-pre-wrap break-words">{JSON.stringify(value, null, 2)}</pre>;
}

// ───────────────────────────── one timeline event ─────────────────────────────

function EventRow({ event }) {
  const d = event.data || {};
  const base = 'rounded-xl border p-3 text-sm';
  switch (event.type) {
    case 'director_narration':
      return (
        <div className={`${base} bg-white/[0.03] border-white/10`}>
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1"><Clapperboard className="w-3.5 h-3.5" /> Director
            <span className="text-gray-500">→ next: <b className="text-gray-300">{d.chosen || d.next_speaker}</b>
              {d.requested && d.requested !== (d.chosen || d.next_speaker) && <> (asked for {d.requested})</>}</span></div>
          {event.content ? <p className="text-gray-300 italic leading-relaxed">{event.content}</p> : <p className="text-gray-500 italic">No narration.</p>}
          {d.override && <p className="text-xs text-amber-300/80 mt-1">Override: {d.override}</p>}
          {d.parse_error && <p className="text-xs text-red-300 mt-1">Could not read the Director's answer: {d.parse_error}</p>}
        </div>
      );
    case 'twist':
      return (
        <div className={`${base} bg-amber-500/10 border-amber-500/40`}>
          <div className="flex items-center gap-2 text-xs font-semibold text-amber-300 mb-1"><Sparkles className="w-3.5 h-3.5" /> DRAMATIC TWIST</div>
          <p className="text-amber-100 leading-relaxed">{event.content}</p>
          {d.world_state_updates && Object.keys(d.world_state_updates).length > 0 && <Collapsible label="World changes"><Json value={d.world_state_updates} /></Collapsible>}
        </div>
      );
    case 'dialogue':
      return (
        <div className={`${base} bg-sky-500/5 border-sky-500/20`}>
          <div className="flex flex-wrap items-center gap-2 text-xs mb-1">
            <MessageSquare className="w-3.5 h-3.5 text-sky-300" /><b className="text-sky-200">{event.speaker}</b>
            {d.decision && <span className="px-1.5 py-0.5 rounded bg-white/10 text-gray-300">{d.decision}</span>}
            {d.retried_after_review && <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">rewritten after review</span>}
            {d.parsed === false && <span className="px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">not valid JSON</span>}
          </div>
          <p className="text-gray-100 leading-relaxed">{event.content}</p>
          {d.reasoning && <div className="mt-2 flex gap-2 text-xs text-gray-400"><Brain className="w-3.5 h-3.5 mt-0.5 shrink-0" /><span className="italic">{d.reasoning}</span></div>}
        </div>
      );
    case 'rejected_dialogue':
      return (
        <div className={`${base} bg-red-500/5 border-red-500/20`}>
          <div className="flex items-center gap-2 text-xs text-red-300 mb-1"><Ban className="w-3.5 h-3.5" /> Rejected draft — {event.speaker}</div>
          <p className="text-gray-400 line-through decoration-red-400/50">{event.content}</p>
          {d.reasoning && <div className="mt-2 flex gap-2 text-xs text-gray-500"><Brain className="w-3.5 h-3.5 mt-0.5 shrink-0" /><span className="italic">{d.reasoning}</span></div>}
        </div>
      );
    case 'review': {
      const rejected = d.rejected;
      return (
        <div className={`${base} ${rejected ? 'bg-red-500/5 border-red-500/20' : 'bg-emerald-500/5 border-emerald-500/15'} py-2`}>
          <div className={`flex items-center gap-2 text-xs ${rejected ? 'text-red-300' : 'text-emerald-300'}`}>
            {rejected ? <ShieldX className="w-3.5 h-3.5" /> : <ShieldCheck className="w-3.5 h-3.5" />}
            Reviewer: {rejected ? 'rejected' : 'approved'}{d.severity && d.severity !== 'none' ? ` (${d.severity})` : ''}
          </div>
          {d.issues?.length > 0 && <ul className="list-disc ml-5 mt-1 text-xs text-gray-400 space-y-0.5">{d.issues.map((i, n) => <li key={n}>{i}</li>)}</ul>}
          {d.suggestion && <p className="text-xs text-gray-300 mt-1">Suggestion: {d.suggestion}</p>}
          {d.note && <p className="text-xs text-gray-500 mt-1">{d.note}</p>}
        </div>
      );
    }
    case 'action':
      return (
        <div className={`${base} ${d.valid ? 'bg-violet-500/5 border-violet-500/20' : 'bg-white/[0.02] border-white/10'} py-2`}>
          <div className="flex flex-wrap items-center gap-2 text-xs text-violet-300">
            <Hand className="w-3.5 h-3.5" /> Action <b>{d.action_type}</b>{d.target && <> → {d.target}</>}
            {!d.valid && <span className="px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">rejected: {d.rejected_reason}</span>}
          </div>
          <p className="text-gray-300 text-xs mt-1">{d.description || event.content}</p>
        </div>
      );
    case 'world_state':
      return <div className="pl-3"><Collapsible label={<span className="inline-flex items-center gap-1"><Globe2 className="w-3.5 h-3.5" /> World state after this turn</span>}><Json value={d.state} /></Collapsible></div>;
    case 'conclusion_check':
      return (
        <div className="flex items-center gap-2 text-xs text-gray-500 pl-3">
          <Scale className="w-3.5 h-3.5" /> Director check: {d.should_end ? 'end the story' : 'keep going'}{event.content ? ` — ${event.content}` : ''}
        </div>
      );
    case 'conclusion':
      return (
        <div className={`${base} bg-emerald-500/10 border-emerald-500/30`}>
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-300 mb-1"><Flag className="w-3.5 h-3.5" /> ENDING {d.trigger && <span className="font-normal text-emerald-400/70">({d.trigger})</span>}</div>
          <p className="text-emerald-50 leading-relaxed">{event.content}</p>
        </div>
      );
    case 'error':
      return (
        <div className={`${base} bg-red-500/10 border-red-500/30`}>
          <div className="flex items-center gap-2 text-xs text-red-300"><AlertTriangle className="w-3.5 h-3.5" /> {event.content}</div>
          {d.error && <p className="text-xs text-red-200/80 mt-1 break-words">{d.error}</p>}
        </div>
      );
    default:
      return <div className={`${base} bg-white/[0.02] border-white/10`}><b className="text-xs text-gray-400">{event.type}</b><p className="text-gray-300">{event.content}</p><Json value={d} /></div>;
  }
}

// ───────────────────────────── LLM calls ─────────────────────────────

function LlmCalls({ token, runId, onError }) {
  const [calls, setCalls] = useState(null);
  useEffect(() => {
    api(`/api/admin/runs/${runId}/llm-calls`, { token }).then((r) => setCalls(r.calls)).catch((e) => onError(e.message));
  }, [token, runId]);
  if (!calls) return <div className="flex items-center gap-2 text-gray-400 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Loading prompts…</div>;
  if (!calls.length) return <p className="text-sm text-gray-500">No LLM calls logged for this run (the log may be off, or older than the retention period).</p>;
  return (
    <div className="space-y-2">
      {calls.map((c, i) => (
        <div key={c.id} className={`rounded-lg border p-2.5 ${c.ok ? 'border-white/10 bg-white/[0.02]' : 'border-red-500/30 bg-red-500/5'}`}>
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
            <span className="text-gray-500">#{i + 1}</span><b className="text-gray-200">{c.agent}</b>
            <span>{c.model || 'unknown model'}</span>{c.latency_ms != null && <span>{(c.latency_ms / 1000).toFixed(1)}s</span>}
            {!c.ok && <span className="text-red-300">failed</span>}
            <span className="ml-auto">{new Date(c.created_at).toLocaleTimeString()}</span>
          </div>
          {c.error && <p className="text-xs text-red-300 mt-1 break-words">{c.error}</p>}
          <div className="mt-1.5 space-y-1">
            <Collapsible label="Prompt"><pre className="text-xs bg-black/40 rounded-lg p-2 max-h-80 overflow-auto whitespace-pre-wrap text-gray-300">{c.prompt}</pre></Collapsible>
            {c.response && <Collapsible label="Response"><pre className="text-xs bg-black/40 rounded-lg p-2 max-h-80 overflow-auto whitespace-pre-wrap text-gray-300">{c.response}</pre></Collapsible>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ───────────────────────────── run detail ─────────────────────────────

function RunDetail({ token, runId, scenarioTitle, onChanged, onDeleted, onError }) {
  const [run, setRun] = useState(null);
  const [tab, setTab] = useState('timeline');
  const [showDetails, setShowDetails] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api(`/api/admin/runs/${runId}`, { token }).then(setRun).catch((e) => onError(e.message));
  }, [token, runId]);

  useEffect(() => { setRun(null); setTab('timeline'); load(); }, [load]);
  useEffect(() => {  // follow a run that is still being generated
    if (run?.status !== 'running') return undefined;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [run?.status, load]);

  const byTurn = useMemo(() => {
    const groups = [];
    for (const e of run?.events ?? []) {
      if (!showDetails && ['world_state', 'conclusion_check', 'review'].includes(e.type) && !e.data?.rejected) continue;
      const key = e.turn ?? 0;
      if (!groups.length || groups[groups.length - 1].turn !== key) groups.push({ turn: key, events: [] });
      groups[groups.length - 1].events.push(e);
    }
    return groups;
  }, [run, showDetails]);

  if (!run) return <div className="flex items-center gap-2 text-gray-400"><Loader2 className="w-4 h-4 animate-spin" /> Loading run…</div>;

  const togglePool = async () => {
    setBusy(true);
    try { setRun(await api(`/api/admin/runs/${runId}`, { token, method: 'PATCH', body: { in_replay_pool: !run.in_replay_pool } })); onChanged(); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete run #${runId} and all its events and prompts permanently? This cannot be undone.`)) return;
    try { await api(`/api/admin/runs/${runId}`, { token, method: 'DELETE' }); onDeleted(); }
    catch (e) { onError(e.message); }
  };

  return (
    <div className="space-y-4 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-gray-100 flex items-center gap-2">Run #{run.id} <StatusBadge status={run.status} /></h2>
          <p className="text-sm text-gray-400">{scenarioTitle || run.title} <span className="text-gray-600">({run.scenario_id}{run.scenario_version ? `, v${run.scenario_version}` : ''})</span> · {run.language === 'english' ? 'English' : 'Roman Urdu'} · {timeAgo(run.started_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={load} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-sm"><RefreshCw className="w-4 h-4" /> Refresh</button>
          <button type="button" onClick={() => downloadJson(`run-${run.id}.json`, run)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-sm"><Download className="w-4 h-4" /> Export</button>
          <button type="button" onClick={remove} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-red-300 hover:bg-red-500/10"><Trash2 className="w-4 h-4" /> Delete</button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-2">
        <Stat label="Started" value={formatDate(run.started_at)} />
        <Stat label="Duration" value={run.duration_seconds != null ? `${Math.floor(run.duration_seconds / 60)}m ${run.duration_seconds % 60}s` : run.status === 'running' ? 'running…' : '—'} />
        <Stat label="Turns / actions" value={`${run.turn_count} / ${run.action_count}`} />
        <Stat label="Twist at turn" value={run.twist_turn ?? 'none'} />
        <Stat label="LLM calls" value={run.llm_call_count} />
        <Stat label="Models" value={(run.models_used || []).join(', ') || '—'} />
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl bg-white/5 border border-white/10 p-3 text-sm">
        <Repeat className="w-4 h-4 text-gray-400" />
        <span className="text-gray-300">Offline replay pool:</span>
        <button type="button" onClick={togglePool} disabled={busy || run.status !== 'completed'}
          title={run.status !== 'completed' ? 'Only completed runs can be replayed' : ''}
          className={`px-3 py-1 rounded-lg text-xs font-semibold disabled:opacity-40 ${run.in_replay_pool ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/10 text-gray-300'}`}>
          {run.in_replay_pool ? 'Included' : 'Excluded'}
        </button>
        <span className="text-gray-500 text-xs">Replayed {run.times_served}× {run.last_served_at ? `(last ${timeAgo(run.last_served_at)})` : ''}</span>
        {run.error && <span className="text-xs text-red-300 break-words">Error: {run.error}</span>}
      </div>

      <div className="flex items-center gap-1 border-b border-white/10">
        {[['timeline', 'Timeline'], ['story', 'As shown to viewers'], ['llm', 'LLM prompts']].map(([k, label]) => (
          <button key={k} type="button" onClick={() => setTab(k)}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${tab === k ? 'border-amber-500 text-amber-300' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>{label}</button>
        ))}
        {tab === 'timeline' && (
          <label className="ml-auto flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
            <input type="checkbox" checked={showDetails} onChange={(e) => setShowDetails(e.target.checked)} /> Show reviews, checks & world state
          </label>
        )}
      </div>

      {tab === 'timeline' && (
        <div className="space-y-5">
          <div className="rounded-xl bg-white/[0.03] border border-white/10 p-3">
            <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Story seed</div>
            <p className="text-sm text-gray-300 leading-relaxed">{run.seed}</p>
          </div>
          {byTurn.length === 0 && <p className="text-sm text-gray-500">No events recorded.</p>}
          {byTurn.map((g) => (
            <section key={`${g.turn}-${g.events[0].seq}`} className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{g.turn ? `Turn ${g.turn}` : 'Before the story'}</h3>
              {g.events.map((e) => <EventRow key={e.seq} event={e} />)}
            </section>
          ))}
        </div>
      )}
      {tab === 'story' && (
        run.turns?.length ? (
          <div className="space-y-3">
            {run.turns.map((t) => (
              <div key={t.turn} className="rounded-xl bg-white/[0.03] border border-white/10 p-3 text-sm">
                <div className="text-xs text-gray-500 mb-1">Turn {t.turn}</div>
                {t.narration && <p className="text-gray-400 italic mb-2">{t.narration}</p>}
                <p><b className="text-sky-200">{t.speaker}:</b> <span className="text-gray-100">{t.dialogue}</span></p>
                {t.actionText && <p className="text-xs text-violet-300 mt-1">{t.actionText}</p>}
              </div>
            ))}
            {run.conclusion && <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/30 p-3 text-sm text-emerald-50">{run.conclusion}</div>}
          </div>
        ) : <p className="text-sm text-gray-500">The final story is saved when the run finishes.</p>
      )}
      {tab === 'llm' && <LlmCalls token={token} runId={run.id} onError={onError} />}
    </div>
  );
}

// ───────────────────────────── list ─────────────────────────────

export default function RunsView({ token, scenarios, onError }) {
  const [filters, setFilters] = useState({ scenario: '', status: '', language: '' });
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const titles = useMemo(() => Object.fromEntries(scenarios.map((s) => [s.id, s.title])), [scenarios]);

  const load = useCallback(async () => {
    setLoading(true);
    const q = new URLSearchParams({ limit: PAGE_SIZE, offset, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) });
    try {
      const res = await api(`/api/admin/runs?${q}`, { token });
      setList(res);
      setSelected((cur) => cur ?? res.runs[0]?.id ?? null);
    } catch (e) { onError(e.message); } finally { setLoading(false); }
  }, [token, filters, offset]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (key, value) => { setOffset(0); setSelected(null); setFilters((f) => ({ ...f, [key]: value })); };
  const counts = list?.status_counts ?? {};

  return (
    <div className="grid lg:grid-cols-[340px_1fr] gap-6">
      <aside className="space-y-3">
        <div className="flex flex-wrap gap-1.5 text-xs">
          {Object.keys(STATUS_STYLES).map((s) => counts[s] ? (
            <button key={s} type="button" onClick={() => setFilter('status', filters.status === s ? '' : s)}
              className={`px-2 py-0.5 rounded-full border ${STATUS_STYLES[s]} ${filters.status === s ? 'ring-1 ring-white/50' : ''}`}>{s} {counts[s]}</button>
          ) : null)}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <select aria-label="Scenario" className={`${inputCls} col-span-2`} value={filters.scenario} onChange={(e) => setFilter('scenario', e.target.value)}>
            <option value="">All scenarios</option>
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
          <select aria-label="Status" className={inputCls} value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            <option value="">Any status</option>
            {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select aria-label="Language" className={inputCls} value={filters.language} onChange={(e) => setFilter('language', e.target.value)}>
            <option value="">Any language</option>
            <option value="urdu">Roman Urdu</option>
            <option value="english">English</option>
          </select>
        </div>
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{list ? `${list.total} run${list.total === 1 ? '' : 's'}` : ''}</span>
          <button type="button" onClick={load} className="inline-flex items-center gap-1 hover:text-gray-300"><RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh</button>
        </div>

        <div className="space-y-1.5">
          {!list && loading && <div className="flex items-center gap-2 text-sm text-gray-400 py-4"><Loader2 className="w-4 h-4 animate-spin" /> Loading runs…</div>}
          {list?.runs.map((r) => (
            <button key={r.id} type="button" onClick={() => setSelected(r.id)}
              className={`w-full text-left rounded-xl border p-3 transition-colors ${selected === r.id ? 'bg-amber-500/10 border-amber-500/50' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-gray-100">#{r.id}</span><StatusBadge status={r.status} />
              </div>
              <div className="text-sm text-gray-300 truncate mt-0.5">{titles[r.scenario_id] || r.title}</div>
              <div className="text-xs text-gray-500 mt-0.5 flex flex-wrap gap-x-2">
                <span>{r.language === 'english' ? 'English' : 'Urdu'}</span><span>{r.turn_count} turns</span>
                {r.in_replay_pool && <span className="text-emerald-400/80">replay pool</span>}<span>{timeAgo(r.started_at)}</span>
              </div>
            </button>
          ))}
          {list && list.runs.length === 0 && <p className="text-sm text-gray-500 py-6 text-center">No runs yet. Start a story in the player — every run is recorded here.</p>}
        </div>
        {list && list.total > PAGE_SIZE && (
          <div className="flex items-center justify-between text-sm">
            <button type="button" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} className="px-3 py-1 rounded-lg bg-white/10 disabled:opacity-30">Newer</button>
            <span className="text-xs text-gray-500">{offset + 1}–{Math.min(offset + PAGE_SIZE, list.total)}</span>
            <button type="button" disabled={offset + PAGE_SIZE >= list.total} onClick={() => setOffset((o) => o + PAGE_SIZE)} className="px-3 py-1 rounded-lg bg-white/10 disabled:opacity-30">Older</button>
          </div>
        )}
        <p className="text-xs text-gray-600 flex items-start gap-1.5"><Cpu className="w-3.5 h-3.5 mt-0.5 shrink-0" /> Every step of every run is stored: narration, twists, dialogue with the character's reasoning, reviewer verdicts, actions, world state, the ending, and each LLM prompt.</p>
      </aside>

      <main className="min-w-0">
        {selected
          ? <RunDetail token={token} runId={selected} scenarioTitle={titles[list?.runs.find((r) => r.id === selected)?.scenario_id]}
              onChanged={load} onDeleted={() => { setSelected(null); load(); }} onError={onError} />
          : <p className="text-sm text-gray-500">Select a run to see its full timeline.</p>}
      </main>
    </div>
  );
}
