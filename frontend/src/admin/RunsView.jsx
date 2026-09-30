import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  RefreshCw, Loader2, Trash2, Download, Brain, ChevronDown, ChevronRight, ChevronLeft, AlertTriangle,
  Clapperboard, Sparkles, MessageSquare, ShieldCheck, ShieldX, Hand, Flag, Globe2, Scale, Ban, Repeat,
} from 'lucide-react';
import { api, fieldCls, btn, cardCls, downloadJson, formatDate, timeAgo } from './common';
import { Card, Badge, Notice, Skeleton, SkeletonRows, SkeletonHeader } from './ui';

const STATUS_TONES = { completed: 'green', incomplete: 'amber', failed: 'rose', aborted: 'gray', running: 'sky' };
const STATUS_LABELS = { completed: 'Completed', incomplete: 'Incomplete', failed: 'Failed', aborted: 'Aborted', running: 'Running' };
const STATUS_HELP = {
  completed: 'Finished with an ending and no failed turns — used for offline replay',
  incomplete: 'Finished, but some turns failed or there was no ending',
  failed: 'Stopped because of an error',
  aborted: 'The viewer left, or the server restarted, before it finished',
  running: 'Still being generated',
};
const STATUS_DOTS = { completed: 'bg-emerald-500', incomplete: 'bg-amber-500', failed: 'bg-rose-500', aborted: 'bg-slate-400', running: 'bg-sky-500' };
const PAGE_SIZE = 30;

function StatusBadge({ status }) {
  return (
    <Badge tone={STATUS_TONES[status] ?? 'gray'} title={STATUS_HELP[status]}>
      {status === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}{STATUS_LABELS[status] ?? status}
    </Badge>
  );
}

function StatTile({ label, value }) {
  return (
    <div className={`${cardCls} p-4`}>
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-lg font-bold text-slate-900 mt-1 break-words">{value ?? '—'}</div>
    </div>
  );
}

function Collapsible({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800">
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />} {label}
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

function Json({ value }) {
  return <pre className="text-xs bg-gray-50 border border-slate-200 rounded-lg p-2.5 overflow-x-auto max-h-64 text-slate-700 whitespace-pre-wrap break-words">{JSON.stringify(value, null, 2)}</pre>;
}

// ───────────────────────────── one timeline event ─────────────────────────────

function EventRow({ event }) {
  const d = event.data || {};
  const base = 'rounded-xl border p-3.5 text-sm';
  const chip = 'px-1.5 py-0.5 rounded-md text-[11px] font-medium';
  switch (event.type) {
    case 'director_narration':
      return (
        <div className={`${base} bg-gray-50 border-gray-200`}>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 mb-1.5"><Clapperboard className="w-3.5 h-3.5" /> Director
            <span>→ next: <b className="text-slate-800">{d.chosen || d.next_speaker}</b>
              {d.requested && d.requested !== (d.chosen || d.next_speaker) && <> (asked for {d.requested})</>}</span></div>
          {event.content ? <p className="text-slate-700 italic leading-relaxed">{event.content}</p> : <p className="text-slate-400 italic">No narration.</p>}
          {d.override && <p className="text-xs text-amber-800 mt-1.5">Override: {d.override}</p>}
          {d.parse_error && <p className="text-xs text-rose-600 mt-1.5">Could not read the Director's answer: {d.parse_error}</p>}
        </div>
      );
    case 'twist':
      return (
        <div className={`${base} bg-amber-50 border-amber-200`}>
          <div className="flex items-center gap-2 text-xs font-semibold text-amber-800 mb-1.5"><Sparkles className="w-3.5 h-3.5" /> Twist</div>
          <p className="text-slate-800 leading-relaxed">{event.content}</p>
          {d.world_state_updates && Object.keys(d.world_state_updates).length > 0 && <div className="mt-2"><Collapsible label="World changes"><Json value={d.world_state_updates} /></Collapsible></div>}
        </div>
      );
    case 'dialogue':
      return (
        <div className={`${base} bg-white border-sky-200`}>
          <div className="flex flex-wrap items-center gap-2 text-xs mb-1.5">
            <MessageSquare className="w-3.5 h-3.5 text-sky-600" /><b className="text-sky-800">{event.speaker}</b>
            {d.decision && <span className={`${chip} bg-slate-100 text-slate-600`}>{d.decision}</span>}
            {d.retried_after_review && <span className={`${chip} bg-amber-50 text-amber-800`}>rewritten after review</span>}
            {d.parsed === false && <span className={`${chip} bg-rose-50 text-rose-700`}>not valid JSON</span>}
          </div>
          <p className="text-slate-900 leading-relaxed">{event.content}</p>
          {d.reasoning && <div className="mt-2 flex gap-2 text-xs text-slate-500"><Brain className="w-3.5 h-3.5 mt-0.5 shrink-0" /><span className="italic">{d.reasoning}</span></div>}
        </div>
      );
    case 'rejected_dialogue':
      return (
        <div className={`${base} bg-rose-50/60 border-rose-200`}>
          <div className="flex items-center gap-2 text-xs font-medium text-rose-700 mb-1.5"><Ban className="w-3.5 h-3.5" /> Rejected draft — {event.speaker}</div>
          <p className="text-slate-500 line-through decoration-rose-400/60">{event.content}</p>
          {d.reasoning && <div className="mt-2 flex gap-2 text-xs text-slate-500"><Brain className="w-3.5 h-3.5 mt-0.5 shrink-0" /><span className="italic">{d.reasoning}</span></div>}
        </div>
      );
    case 'review': {
      const rejected = d.rejected;
      return (
        <div className={`${base} py-2.5 ${rejected ? 'bg-rose-50/60 border-rose-200' : 'bg-emerald-50/60 border-emerald-200'}`}>
          <div className={`flex items-center gap-2 text-xs font-medium ${rejected ? 'text-rose-700' : 'text-emerald-700'}`}>
            {rejected ? <ShieldX className="w-3.5 h-3.5" /> : <ShieldCheck className="w-3.5 h-3.5" />}
            Reviewer: {rejected ? 'rejected' : 'approved'}{d.severity && d.severity !== 'none' ? ` (${d.severity})` : ''}
          </div>
          {d.issues?.length > 0 && <ul className="list-disc ml-5 mt-1.5 text-xs text-slate-600 space-y-0.5">{d.issues.map((i, n) => <li key={n}>{i}</li>)}</ul>}
          {d.suggestion && <p className="text-xs text-slate-700 mt-1.5">Suggestion: {d.suggestion}</p>}
          {d.note && <p className="text-xs text-slate-500 mt-1">{d.note}</p>}
        </div>
      );
    }
    case 'action':
      return (
        <div className={`${base} py-2.5 ${d.valid ? 'bg-violet-50/60 border-violet-200' : 'bg-gray-50 border-gray-200'}`}>
          <div className="flex flex-wrap items-center gap-2 text-xs text-violet-700">
            <Hand className="w-3.5 h-3.5" /> Action <b>{d.action_type}</b>{d.target && <> → {d.target}</>}
            {!d.valid && <span className={`${chip} bg-rose-50 text-rose-700`}>rejected: {d.rejected_reason}</span>}
          </div>
          <p className="text-slate-700 text-xs mt-1">{d.description || event.content}</p>
        </div>
      );
    case 'world_state':
      return <div className="pl-3"><Collapsible label={<span className="inline-flex items-center gap-1"><Globe2 className="w-3.5 h-3.5" /> World state after this turn</span>}><Json value={d.state} /></Collapsible></div>;
    case 'conclusion_check':
      return (
        <div className="flex items-center gap-2 text-xs text-slate-500 pl-3">
          <Scale className="w-3.5 h-3.5" /> Director check: {d.should_end ? 'end the story' : 'keep going'}{event.content ? ` — ${event.content}` : ''}
        </div>
      );
    case 'conclusion':
      return (
        <div className={`${base} bg-emerald-50 border-emerald-200`}>
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-800 mb-1.5"><Flag className="w-3.5 h-3.5" /> Ending {d.trigger && <span className="font-normal text-emerald-700/80">({d.trigger})</span>}</div>
          <p className="text-slate-800 leading-relaxed">{event.content}</p>
        </div>
      );
    case 'error':
      return (
        <div className={`${base} bg-rose-50 border-rose-200`}>
          <div className="flex items-center gap-2 text-xs font-medium text-rose-700"><AlertTriangle className="w-3.5 h-3.5" /> {event.content}</div>
          {d.error && <p className="text-xs text-rose-700/80 mt-1 break-words">{d.error}</p>}
        </div>
      );
    default:
      return <div className={`${base} bg-gray-50 border-gray-200`}><b className="text-xs text-slate-500">{event.type}</b><p className="text-slate-700">{event.content}</p><Json value={d} /></div>;
  }
}

// ───────────────────────────── LLM calls ─────────────────────────────

function LlmCalls({ token, runId, onError }) {
  const [calls, setCalls] = useState(null);
  useEffect(() => {
    api(`/api/admin/runs/${runId}/llm-calls`, { token }).then((r) => setCalls(r.calls)).catch((e) => onError(e.message));
  }, [token, runId]);
  if (!calls) {
    return (
      <div className="space-y-2.5" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl border border-gray-200 bg-white p-3.5 space-y-2.5">
            <div className="flex gap-3"><Skeleton className="h-3.5 w-8" /><Skeleton className="h-3.5 w-28" /><Skeleton className="h-3.5 w-36" /><Skeleton className="h-3.5 w-16 ml-auto" /></div>
            <Skeleton className="h-3 w-20" />
          </div>
        ))}
      </div>
    );
  }
  if (!calls.length) return <p className="text-sm text-slate-500">No LLM calls logged for this run (the log may be off, or older than the retention period).</p>;
  return (
    <div className="space-y-2.5">
      {calls.map((c, i) => (
        <div key={c.id} className={`rounded-xl border p-3.5 ${c.ok ? 'border-gray-200 bg-white' : 'border-rose-200 bg-rose-50/60'}`}>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="text-slate-400">#{i + 1}</span><b className="text-slate-800">{c.agent}</b>
            <span>{c.model || 'unknown model'}</span>{c.latency_ms != null && <span>{(c.latency_ms / 1000).toFixed(1)}s</span>}
            {!c.ok && <Badge tone="rose">Failed</Badge>}
            <span className="ml-auto">{new Date(c.created_at).toLocaleTimeString()}</span>
          </div>
          {c.error && <p className="text-xs text-rose-700 mt-1.5 break-words">{c.error}</p>}
          <div className="mt-2 space-y-1.5">
            <Collapsible label="Prompt"><pre className="text-xs bg-gray-50 border border-slate-200 rounded-lg p-2.5 max-h-80 overflow-auto whitespace-pre-wrap text-slate-700">{c.prompt}</pre></Collapsible>
            {c.response && <Collapsible label="Response"><pre className="text-xs bg-gray-50 border border-slate-200 rounded-lg p-2.5 max-h-80 overflow-auto whitespace-pre-wrap text-slate-700">{c.response}</pre></Collapsible>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ───────────────────────────── run detail ─────────────────────────────

function RunDetail({ token, runId, scenarioTitle, onBack, onChanged, onDeleted, onError }) {
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

  const back = <button type="button" onClick={onBack} className={btn.ghost}><ChevronLeft className="w-4 h-4" /> All stories</button>;
  if (!run) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="-ml-3">{back}</div>
        <SkeletonHeader actions={3} />
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 space-y-2"><Skeleton className="h-3 w-16" /><Skeleton className="h-5 w-24" /></div>
          ))}
        </div>
        <div className="space-y-2.5">
          <Skeleton className="h-3 w-16" />
          {['h-20', 'h-24', 'h-12', 'h-20'].map((h, i) => <Skeleton key={i} className={`${h} w-full rounded-xl`} />)}
        </div>
      </div>
    );
  }

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
    <div className="space-y-6 min-w-0">
      <div className="-ml-3">{back}</div>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl! leading-tight! font-bold text-gray-900 tracking-tight">Run #{run.id}</h1>
            <StatusBadge status={run.status} />
          </div>
          <p className="text-sm text-gray-500 mt-1">
            {scenarioTitle || run.title} <span className="text-slate-400">({run.scenario_id}{run.scenario_version ? `, v${run.scenario_version}` : ''})</span> · {run.language === 'english' ? 'English' : 'Roman Urdu'} · {timeAgo(run.started_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={load} className={btn.secondary}><RefreshCw className="w-4 h-4" /> Refresh</button>
          <button type="button" onClick={() => downloadJson(`run-${run.id}.json`, run)} className={btn.secondary}><Download className="w-4 h-4" /> Export</button>
          <button type="button" onClick={remove} className={btn.danger}><Trash2 className="w-4 h-4" /> Delete</button>
        </div>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatTile label="Started" value={formatDate(run.started_at)} />
        <StatTile label="Duration" value={run.duration_seconds != null ? `${Math.floor(run.duration_seconds / 60)}m ${run.duration_seconds % 60}s` : run.status === 'running' ? 'Running…' : '—'} />
        <StatTile label="Turns / actions" value={`${run.turn_count} / ${run.action_count}`} />
        <StatTile label="Twist at turn" value={run.twist_turn ?? 'None'} />
        <StatTile label="LLM calls" value={run.llm_call_count} />
        <StatTile label="Models" value={(run.models_used || []).join(', ') || '—'} />
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Repeat className="w-4 h-4 text-slate-400" />
          <span className="font-medium text-slate-800">Offline replay pool</span>
          <button type="button" onClick={togglePool} disabled={busy || run.status !== 'completed'}
            title={run.status !== 'completed' ? 'Only completed runs can be replayed' : ''}
            className={run.in_replay_pool ? `${btn.small} bg-emerald-50! border-emerald-200! text-emerald-700! hover:bg-emerald-100!` : btn.small}>
            {run.in_replay_pool ? 'Included' : 'Excluded'}
          </button>
          <span className="text-slate-500 text-xs">Replayed {run.times_served}× {run.last_served_at ? `(last ${timeAgo(run.last_served_at)})` : ''}</span>
        </div>
        {run.error && <div className="mt-4"><Notice tone="error">Error: {run.error}</Notice></div>}
      </Card>

      <div className="flex flex-wrap items-end gap-x-6 gap-y-3 border-b border-gray-200">
        {[['timeline', 'Timeline'], ['story', 'As shown to viewers'], ['llm', 'LLM prompts']].map(([k, label]) => (
          <button key={k} type="button" onClick={() => setTab(k)} aria-current={tab === k}
            className={`pb-3 -mb-px border-b-2 text-sm font-medium transition-colors ${tab === k ? 'border-amber-700 text-amber-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>{label}</button>
        ))}
        {tab === 'timeline' && (
          <label className="ml-auto pb-3 flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
            <input type="checkbox" className="accent-amber-700" checked={showDetails} onChange={(e) => setShowDetails(e.target.checked)} /> Show reviews, checks & world state
          </label>
        )}
      </div>

      {tab === 'timeline' && (
        <div className="space-y-6">
          <Card title="Story seed"><p className="text-sm text-slate-700 leading-relaxed">{run.seed}</p></Card>
          {byTurn.length === 0 && <p className="text-sm text-slate-500">No events recorded.</p>}
          {byTurn.map((g) => (
            <section key={`${g.turn}-${g.events[0].seq}`} className="space-y-2.5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{g.turn ? `Turn ${g.turn}` : 'Before the story'}</h3>
              {g.events.map((e) => <EventRow key={e.seq} event={e} />)}
            </section>
          ))}
        </div>
      )}
      {tab === 'story' && (
        run.turns?.length ? (
          <div className="space-y-3">
            {run.turns.map((t) => (
              <div key={t.turn} className="rounded-xl bg-white border border-gray-200 p-4 text-sm">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1.5">Turn {t.turn}</div>
                {t.narration && <p className="text-slate-500 italic mb-2">{t.narration}</p>}
                <p><b className="text-sky-800">{t.speaker}:</b> <span className="text-slate-900">{t.dialogue}</span></p>
                {t.actionText && <p className="text-xs text-violet-700 mt-1.5">{t.actionText}</p>}
              </div>
            ))}
            {run.conclusion && <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-sm text-slate-800">{run.conclusion}</div>}
          </div>
        ) : <p className="text-sm text-slate-500">The final story is saved when the run finishes.</p>
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
      setList(await api(`/api/admin/runs?${q}`, { token }));
    } catch (e) { onError(e.message); } finally { setLoading(false); }
  }, [token, filters, offset]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (key, value) => { setOffset(0); setFilters((f) => ({ ...f, [key]: value })); };
  const counts = list?.status_counts ?? {};

  if (selected) {
    const row = list?.runs.find((r) => r.id === selected);
    return (
      <RunDetail token={token} runId={selected} scenarioTitle={titles[row?.scenario_id]}
        onBack={() => setSelected(null)} onChanged={load} onDeleted={() => { setSelected(null); load(); }} onError={onError} />
    );
  }

  const th = 'px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wide text-left whitespace-nowrap';
  const td = 'px-5 py-4 text-sm text-slate-700 whitespace-nowrap';

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl! leading-tight! font-bold text-gray-900 tracking-tight">Stories</h1>
          <p className="text-sm text-gray-500 mt-1">Every story run, step by step: narration, dialogue with reasoning, reviewer verdicts, actions and each LLM prompt.</p>
        </div>
        <button type="button" onClick={load} className={btn.secondary}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {Object.keys(STATUS_LABELS).map((s) => {
          const active = filters.status === s;
          return (
            <button key={s} type="button" onClick={() => setFilter('status', active ? '' : s)} aria-pressed={active} title={STATUS_HELP[s]}
              className={`${cardCls} p-4 text-left ${active ? 'ring-2 ring-amber-700/60' : ''}`}>
              <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-slate-400">
                <span className={`w-2 h-2 rounded-full ${STATUS_DOTS[s]}`} />{STATUS_LABELS[s]}
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">{list ? counts[s] ?? 0 : '—'}</div>
            </button>
          );
        })}
      </div>

      <Card padded={false}>
        <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-gray-100">
          <select aria-label="Scenario" className={`${fieldCls} w-full sm:w-64`} value={filters.scenario} onChange={(e) => setFilter('scenario', e.target.value)}>
            <option value="">All scenarios</option>
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
          <select aria-label="Status" className={`${fieldCls} w-full sm:w-44`} value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            <option value="">Any status</option>
            {Object.entries(STATUS_LABELS).map(([s, label]) => <option key={s} value={s}>{label}</option>)}
          </select>
          <select aria-label="Language" className={`${fieldCls} w-full sm:w-44`} value={filters.language} onChange={(e) => setFilter('language', e.target.value)}>
            <option value="">Any language</option>
            <option value="urdu">Roman Urdu</option>
            <option value="english">English</option>
          </select>
          <span className="sm:ml-auto text-sm text-slate-500">{list ? `${list.total} run${list.total === 1 ? '' : 's'}` : ''}</span>
        </div>

        {!list ? <SkeletonRows rows={6} cols={7} /> : list.runs.length === 0 ? (
          <p className="text-sm text-slate-500 py-12 text-center">No runs yet. Start a story in the player — every run is recorded here.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>{['Run', 'Scenario', 'Status', 'Language', 'Turns', 'Replay', 'Started'].map((h) => <th key={h} className={th}>{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {list.runs.map((r) => (
                  <tr key={r.id} onClick={() => setSelected(r.id)} className="hover:bg-gray-50 cursor-pointer">
                    <td className={td}>
                      <button type="button" onClick={(e) => { e.stopPropagation(); setSelected(r.id); }} className="font-semibold text-slate-900 hover:text-amber-800">#{r.id}</button>
                    </td>
                    <td className={`${td} max-w-xs truncate`}>{titles[r.scenario_id] || r.title}</td>
                    <td className={td}><StatusBadge status={r.status} /></td>
                    <td className={td}>{r.language === 'english' ? 'English' : 'Roman Urdu'}</td>
                    <td className={td}>{r.turn_count}</td>
                    <td className={td}>{r.in_replay_pool ? <Badge tone="green">In pool</Badge> : <span className="text-slate-400">—</span>}</td>
                    <td className={`${td} text-slate-500`} title={formatDate(r.started_at)}>{timeAgo(r.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {list && list.total > PAGE_SIZE && (
          <div className="flex items-center justify-between px-5 py-3.5 border-t border-gray-100 text-sm">
            <button type="button" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} className={btn.small}>Newer</button>
            <span className="text-xs text-slate-500">{offset + 1}–{Math.min(offset + PAGE_SIZE, list.total)} of {list.total}</span>
            <button type="button" disabled={offset + PAGE_SIZE >= list.total} onClick={() => setOffset((o) => o + PAGE_SIZE)} className={btn.small}>Older</button>
          </div>
        )}
      </Card>
    </div>
  );
}
