import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, Play, RotateCcw, Volume2, Square, Settings, History, Home as HomeIcon, X, Loader2, StepForward } from 'lucide-react';
import { Button } from './components/button';
import { API_BASE, assetUrl, colorsFor } from './lib/api';
import './App.css';

// Character picture, or a coloured initial when no image has been added yet (e.g. AI-generated scenarios).
function CharacterPicture({ image, name, color, className, large = false }) {
  // Falls back to initials if the image can't load (e.g. the database is offline).
  const [failedSrc, setFailedSrc] = useState(null);
  if (image && failedSrc !== image) return <img src={assetUrl(image)} alt={name} className={className} onError={() => setFailedSrc(image)} />;
  const initials = (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  return (
    <div role="img" aria-label={name}
      className={`${large ? 'w-32 h-32 md:w-44 md:h-44 text-4xl md:text-5xl' : 'w-full h-full text-lg'} rounded-full bg-linear-to-br ${colorsFor(color).bg} text-white font-bold flex items-center justify-center shadow-2xl`}>
      {initials}
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch (_) { return ''; }
}

// Saved runs: play any of them again, or continue an unfinished one.
function StoryLibrary({ scenarioId, scenarios, version, onPlay, onContinue, onClose }) {
  const [scope, setScope] = useState('scenario');
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState('');
  const titles = Object.fromEntries(scenarios.map((sc) => [sc.id, sc.title]));

  useEffect(() => {
    const controller = new AbortController();
    const q = scope === 'scenario' && scenarioId ? `scenario=${encodeURIComponent(scenarioId)}&` : '';
    fetch(`${API_BASE}/api/runs?${q}limit=100`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => { setError(''); setRuns(data.runs ?? []); })
      .catch((e) => { if (e?.name !== 'AbortError') setError('Saved stories could not be loaded.'); });
    return () => controller.abort();
  }, [scope, scenarioId, version]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="library-title">
      <div className="w-full max-w-3xl max-h-[85vh] flex flex-col bg-gray-900 border border-white/10 rounded-2xl shadow-2xl">
        <div className="flex items-center gap-3 p-5 border-b border-white/10">
          <History className="w-5 h-5 text-amber-300" />
          <h2 id="library-title" className="text-xl font-bold text-amber-300 flex-1">Purani stories</h2>
          <div className="flex rounded-lg overflow-hidden border border-white/15 text-xs">
            {[['scenario', 'Is kahani ki'], ['all', 'Sab']].map(([key, label]) => (
              <button key={key} type="button" onClick={() => { if (key !== scope) { setRuns(null); setScope(key); } }}
                className={`px-3 py-1.5 ${scope === key ? 'bg-amber-500 text-black font-semibold' : 'bg-white/5 text-gray-300 hover:bg-white/10'}`}>
                {label}
              </button>
            ))}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto p-3 space-y-2">
          {error && <p className="p-4 text-sm text-red-400">{error}</p>}
          {!error && runs === null && (
            <p className="p-4 text-sm text-gray-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</p>
          )}
          {runs?.length === 0 && (
            <p className="p-6 text-center text-gray-400">Abhi koi saved story nahi. Nayi story chalayein — har run yahan save hota hai.</p>
          )}
          {runs?.map((run) => (
            <div key={run.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-white/5 border border-white/10 p-3">
              <div className="flex-1 min-w-52">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-gray-100 font-medium">{titles[run.scenario_id] ?? run.title}</span>
                  <span className="text-xs text-gray-500">Run #{run.id}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                  <span className={`px-2 py-0.5 rounded-full ${run.complete ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}`}>
                    {run.complete ? 'Poori' : 'Adhoori'} · {run.turn_count} turns
                  </span>
                  <span className="text-gray-400">{run.language === 'english' ? 'English' : 'Roman Urdu'}</span>
                  <span className="text-gray-500">{formatDate(run.started_at)}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => onPlay(run)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-sm text-gray-100">
                  <Play className="w-4 h-4" /> Play
                </button>
                {run.can_continue && (
                  <button type="button" onClick={() => onContinue(run)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-sm text-black font-semibold">
                    <StepForward className="w-4 h-4" /> Continue
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function WaveformIcon() {
  const bar = (delay) => (
    <span
      style={{
        display: 'inline-block',
        width: '2px',
        borderRadius: '9999px',
        background: 'currentColor',
        animation: 'waveBar 0.8s ease-in-out infinite',
        animationDelay: delay,
        transformOrigin: 'bottom',
      }}
    />
  );
  return (
    <span style={{ display: 'inline-flex', alignItems: 'flex-end', gap: '2px', height: '12px' }}>
      {bar('0ms')}
      {bar('160ms')}
      {bar('320ms')}
    </span>
  );
}

export default function Home() {
  const [storyData, setStoryData] = useState(null);
  const [currentTurn, setCurrentTurn] = useState(-1);
  const [showDialogue, setShowDialogue] = useState(false);
  const [isAutoPlaying, setIsAutoPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [runError, setRunError] = useState(null);
  const [language, setLanguage] = useState('urdu');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isTTSLoading, setIsTTSLoading] = useState(false);
  const [isNarrationExpanded, setIsNarrationExpanded] = useState(false);
  // Phase 3-A: typewriter
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const typingTimerRef = useRef(null);
  const dialogueBodyRef = useRef(null);
  const audioRef = useRef(null);
  const isAutoPlayingRef = useRef(false);

  const [scenarios, setScenarios] = useState([]);
  const [scenarioId, setScenarioId] = useState(null);
  const [scenarioInfo, setScenarioInfo] = useState(null);
  const [continuable, setContinuable] = useState(null);   // newest unfinished run of this scenario
  const [showLibrary, setShowLibrary] = useState(false);
  const [libraryVersion, setLibraryVersion] = useState(0); // bump to refresh saved-run lists

  const totalTurns = storyData?.turns?.length ?? 0;

  const characters = scenarioInfo?.characters ?? [];
  const charByKey = Object.fromEntries(characters.map((c) => [c.key, c]));
  const colorsOf = (key) => colorsFor(charByKey[key]?.color);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      let lastScenario = null;
      try {
        const res = await fetch(`${API_BASE}/api/story`, { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          // Open on the menu (Continue / New / Saved stories); only remember which scenario was last used.
          if (data?.turns?.length) lastScenario = data.scenarioId ?? null;
        }
      } catch (_) {}
      try {
        const res = await fetch(`${API_BASE}/api/scenarios`, { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          setScenarios(data.scenarios ?? []);
          setScenarioId(lastScenario ?? data.default ?? data.scenarios?.[0]?.id ?? null);
        }
      } catch (_) {}
    })();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!scenarioId) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/api/scenarios/${encodeURIComponent(scenarioId)}`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setScenarioInfo(data))
      .catch(() => {});
    return () => controller.abort();
  }, [scenarioId]);

  useEffect(() => {
    if (!scenarioId) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/api/runs?scenario=${encodeURIComponent(scenarioId)}&continuable=true&limit=1`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setContinuable(data?.runs?.[0] ?? null))
      .catch(() => {});
    return () => controller.abort();
  }, [scenarioId, libraryVersion]);

  useEffect(() => {
    if (currentTurn >= 0) {
      stopAudio();
      setIsNarrationExpanded(false);
      const timer = setTimeout(() => setShowDialogue(true), 500);
      return () => clearTimeout(timer);
    }
  }, [currentTurn]);

  useEffect(() => {
    isAutoPlayingRef.current = isAutoPlaying;
    if (isAutoPlaying && currentData) {
      if (currentTurn >= totalTurns - 1) {
        setIsAutoPlaying(false);
        isAutoPlayingRef.current = false;
      } else {
        speakTurn(currentData, true);
      }
    }
  }, [currentTurn, isAutoPlaying]);

  // Phase 3-A: typewriter effect — fires when showDialogue turns true
  useEffect(() => {
    if (!showDialogue || !currentData?.dialogue) {
      setDisplayedText('');
      setIsTyping(false);
      return;
    }
    const fullText = currentData.dialogue;
    setDisplayedText('');
    setIsTyping(true);
    let i = 0;
    const tick = () => {
      i++;
      setDisplayedText(fullText.slice(0, i));
      if (i < fullText.length) {
        typingTimerRef.current = setTimeout(tick, 22);
      } else {
        setIsTyping(false);
      }
    };
    typingTimerRef.current = setTimeout(tick, 22);
    return () => clearTimeout(typingTimerRef.current);
  }, [showDialogue, currentTurn]);

  // Keep the newest typed line in view when a long dialogue scrolls inside the bubble
  useEffect(() => {
    const el = dialogueBodyRef.current;
    if (el && isTyping) el.scrollTop = el.scrollHeight;
  }, [displayedText, isTyping]);

  const skipTyping = () => {
    if (isTyping && currentData?.dialogue) {
      clearTimeout(typingTimerRef.current);
      setDisplayedText(currentData.dialogue);
      setIsTyping(false);
    }
  };

  const openStream = (url) => {
    setIsLoading(true);
    setRunError(null);
    setStoryData(null);
    setCurrentTurn(-1);
    const es = new EventSource(url);
    let story = { title: null, scenario: null, turns: [], conclusion: "" };
    let resumed = false;
    let jumped = false;
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "meta") {
          resumed = Boolean(data.resumed);
          story = { title: data.title, scenario: data.scenario, turns: [], conclusion: "", runId: data.runId };
          setStoryData({ ...story });
        } else if (data.type === "turns" && Array.isArray(data.newTurns)) {
          const prevLen = story.turns.length;
          story.turns = [...story.turns, ...data.newTurns];
          setStoryData({ ...story });
          if (resumed && !jumped) {
            // Continuing: jump to the last saved turn; new turns follow from there.
            jumped = true;
            setCurrentTurn(story.turns.length - 1);
          } else {
            setCurrentTurn((prev) => (prev === prevLen - 1 && prev >= 0 ? story.turns.length - 1 : prev));
          }
        } else if (data.type === "conclusion") {
          story.conclusion = data.conclusion ?? "";
          setStoryData({ ...story });
        } else if (data.type === "done") {
          es.close();
          if (!resumed) setCurrentTurn(-1);
          setIsLoading(false);
          setLibraryVersion((v) => v + 1);
        } else if (data.type === "error") {
          es.close();
          setIsLoading(false);
          setRunError(data.message || "Story could not be started. Please try again.");
          setLibraryVersion((v) => v + 1);
        }
      } catch (_) {}
    };
    es.onerror = () => {
      es.close();
      setIsLoading(false);
      setRunError("Connection lost or server error. Your progress up to the last turn is saved — use Continue.");
      setLibraryVersion((v) => v + 1);
    };
  };

  const startStory = () => {
    openStream(`${API_BASE}/api/run/stream?lang=${language}&scenario=${encodeURIComponent(scenarioId ?? "")}`);
  };

  const continueRun = (run) => {
    setShowLibrary(false);
    if (run.scenario_id !== scenarioId) setScenarioId(run.scenario_id);
    setLanguage(run.language);
    openStream(`${API_BASE}/api/run/stream?continue_run=${run.id}`);
  };

  const playRun = async (run) => {
    setRunError(null);
    try {
      const res = await fetch(`${API_BASE}/api/runs/${run.id}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setShowLibrary(false);
      if (data.scenario_id !== scenarioId) setScenarioId(data.scenario_id);
      setStoryData({ title: data.title, scenario: data.scenario, turns: data.turns, conclusion: data.conclusion, runId: data.id });
      setShowDialogue(false);
      setCurrentTurn(-1);
    } catch (_) {
      setRunError(`Run #${run.id} could not be loaded.`);
    }
  };

  const backToMenu = () => {
    stopAudio();
    isAutoPlayingRef.current = false;
    setIsAutoPlaying(false);
    setShowDialogue(false);
    setCurrentTurn(-1);
    setStoryData(null);
    setLibraryVersion((v) => v + 1);
  };

  const goNext = () => {
    if (currentTurn < totalTurns) {
      setShowDialogue(false);
      setTimeout(() => setCurrentTurn(prev => prev + 1), 300);
    }
  };

  const goPrev = () => {
    if (currentTurn > -1) {
      setShowDialogue(false);
      setTimeout(() => setCurrentTurn(prev => prev - 1), 300);
    }
  };

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setIsSpeaking(false);
    setIsTTSLoading(false);
  };

  const speakTurn = async (turn, autoAdvance = false) => {
    if (!turn) return;
    stopAudio();
    const text = turn.dialogue || "";
    if (!text.trim()) return;
    const speaker = charByKey[turn.character]?.name || turn.speaker || "";
    setIsTTSLoading(true);
    let blobUrl = null;
    try {
      const res = await fetch(
        `${API_BASE}/api/tts?text=${encodeURIComponent(text)}&speaker=${encodeURIComponent(speaker)}&scenario=${encodeURIComponent(scenarioId ?? "")}`
      );
      if (!res.ok) { setIsTTSLoading(false); return; }
      const blob = await res.blob();
      blobUrl = URL.createObjectURL(blob);
    } catch (_) {
      setIsTTSLoading(false);
      return;
    }
    if (!isAutoPlayingRef.current && autoAdvance) { URL.revokeObjectURL(blobUrl); return; }
    const audio = new Audio(blobUrl);
    audioRef.current = audio;
    setIsTTSLoading(false);
    setIsSpeaking(true);
    audio.onended = () => {
      setIsSpeaking(false);
      audioRef.current = null;
      URL.revokeObjectURL(blobUrl);
      if (autoAdvance && isAutoPlayingRef.current) {
        setShowDialogue(false);
        setTimeout(() => setCurrentTurn(prev => prev + 1), 300);
      }
    };
    audio.onerror = () => {
      setIsSpeaking(false);
      audioRef.current = null;
      URL.revokeObjectURL(blobUrl);
    };
    audio.play().catch(() => {
      setIsSpeaking(false);
      audioRef.current = null;
    });
  };

  const toggleAutoPlay = () => {
    const next = !isAutoPlaying;
    isAutoPlayingRef.current = next;
    if (!next) stopAudio();
    setIsAutoPlaying(next);
  };

  const restart = () => {
    stopAudio();
    isAutoPlayingRef.current = false;
    setShowDialogue(false);
    setCurrentTurn(-1);
    setIsAutoPlaying(false);
  };

  const currentData = storyData && currentTurn >= 0 && currentTurn < totalTurns ? storyData.turns[currentTurn] : null;
  const isConclusion = totalTurns > 0 && currentTurn >= totalTurns;
  const isOnLastTurnWhileStreaming = isLoading && totalTurns > 0 && currentTurn === totalTurns - 1;
  const isNextDisabled = isConclusion || isOnLastTurnWhileStreaming;

  return (
    <div className="min-h-screen bg-black flex flex-col">
      {showLibrary && (
        <StoryLibrary scenarioId={scenarioId} scenarios={scenarios} version={libraryVersion}
          onPlay={playRun} onContinue={continueRun} onClose={() => setShowLibrary(false)} />
      )}

      {/* ── Full-bleed scene ── */}
      <div className="relative overflow-hidden flex-1" style={{ minHeight: 'calc(100vh - 260px)' }}>
        {scenarioInfo && !scenarioInfo.background_image ? (
          <div className="absolute inset-0 bg-linear-to-br from-gray-900 via-slate-900 to-black" />
        ) : (
          <img
            src={assetUrl(scenarioInfo?.background_image) || "/img12.png"}
            alt="Scene"
            className="absolute inset-0 w-full h-full object-cover"
          />
        )}
        <div className="absolute inset-0 bg-linear-to-t from-black/80 via-black/10 to-black/50" />

        {/* Title overlay */}
        <div className="absolute top-0 left-0 right-0 z-10 px-6 pt-5 pb-10 bg-linear-to-b from-black/70 to-transparent pointer-events-none">
          <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight drop-shadow-lg">
            {storyData?.title ?? scenarioInfo?.title ?? ""}
          </h1>
          {scenarioInfo?.subtitle && <p className="text-amber-300/80 text-sm mt-0.5">{scenarioInfo.subtitle}</p>}
        </div>

        {/* Start Story */}
        <AnimatePresence>
          {(!storyData || (storyData.turns?.length === 0 && !isLoading)) && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 flex items-center justify-center p-6 z-20"
            >
              <div className="bg-black/60 backdrop-blur-md rounded-2xl p-8 max-w-2xl w-full shadow-2xl border border-white/10">
                <h2 className="text-3xl font-bold text-amber-300 mb-4">Kahani shuru karein</h2>

                {continuable && !isLoading && (
                  <div className="mb-6 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-48">
                      <p className="text-amber-300 font-semibold">Adhoori kahani mili</p>
                      <p className="text-gray-300 text-sm">
                        Run #{continuable.id} · {continuable.turn_count} turns · {continuable.language === 'english' ? 'English' : 'Roman Urdu'} · {formatDate(continuable.started_at)}
                      </p>
                    </div>
                    <Button onClick={() => continueRun(continuable)}
                      className="bg-amber-500 hover:bg-amber-400 text-black font-semibold px-5 py-2.5">
                      <StepForward className="w-4 h-4 mr-1.5" /> Continue
                    </Button>
                  </div>
                )}

                <p className="text-gray-200 leading-relaxed mb-4">
                  Nayi kahani: AI har dafa naye sire se likhta hai. Is mein kuch minute lag sakte hain.
                </p>

                {/* Scenario picker */}
                {scenarios.length > 0 && (
                  <div className="mb-6">
                    <label htmlFor="scenario" className="block text-gray-400 text-sm mb-3 text-center">Kahani / Scenario</label>
                    <select
                      id="scenario"
                      value={scenarioId ?? ""}
                      onChange={(e) => setScenarioId(e.target.value)}
                      className="block mx-auto bg-white/10 border border-white/20 text-gray-100 rounded-xl px-4 py-2.5 text-sm min-w-64"
                    >
                      {scenarios.map((sc) => (
                        <option key={sc.id} value={sc.id} className="bg-gray-900">{sc.title}</option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Language toggle */}
                <div className="mb-6">
                  <p className="text-gray-400 text-sm mb-3 text-center">Zaban / Language</p>
                  <div className="flex rounded-xl overflow-hidden border border-white/20 w-fit mx-auto">
                    <button
                      onClick={() => setLanguage('urdu')}
                      className={`px-6 py-2.5 text-sm font-semibold transition-all ${
                        language === 'urdu'
                          ? 'bg-amber-500 text-black'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      Roman Urdu
                    </button>
                    <button
                      onClick={() => setLanguage('english')}
                      className={`px-6 py-2.5 text-sm font-semibold transition-all ${
                        language === 'english'
                          ? 'bg-amber-500 text-black'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      English
                    </button>
                  </div>
                </div>

                {runError && <p className="text-red-400 text-sm mb-4">{runError}</p>}
                <div className="mt-6 flex gap-4 justify-center">
                  <Button
                    onClick={startStory}
                    disabled={isLoading}
                    className="bg-linear-to-r from-amber-600 to-orange-600 hover:from-amber-700 hover:to-orange-700 text-white px-8 py-3 text-lg disabled:opacity-60"
                  >
                    {isLoading ? "Running story..." : "New story"}
                  </Button>
                  <Button
                    onClick={() => setShowLibrary(true)}
                    disabled={isLoading}
                    className="bg-white/10 hover:bg-white/20 text-gray-100 px-6 py-3 text-lg disabled:opacity-60"
                  >
                    <History className="w-5 h-5 mr-2" /> Purani stories
                  </Button>
                </div>
                <a href="/admin" className="mt-6 flex items-center justify-center gap-1.5 text-xs text-gray-400! hover:text-amber-300!">
                  <Settings className="w-3.5 h-3.5" /> Admin panel
                </a>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Streaming loader */}
        <AnimatePresence>
          {storyData && storyData.turns.length === 0 && isLoading && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 flex items-center justify-center p-6 z-20"
            >
              <div className="bg-black/60 backdrop-blur-md rounded-2xl p-8 max-w-2xl w-full shadow-2xl border border-white/10">
                <h2 className="text-3xl font-bold text-amber-300 mb-4">Streaming story</h2>
                <p className="text-gray-200 text-lg leading-relaxed">
                  Waiting for first turn... turns will appear here as they arrive.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Scene setting */}
        <AnimatePresence>
          {storyData && storyData.turns.length > 0 && currentTurn === -1 && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 flex items-center justify-center p-6 z-20"
            >
              <div className="bg-black/60 backdrop-blur-md rounded-2xl p-8 max-w-2xl w-full shadow-2xl border border-white/10">
                <h2 className="text-3xl font-bold text-amber-300 mb-4">Scene Setting</h2>
                <p className="text-gray-200 text-lg leading-relaxed">{storyData.scenario}</p>
                <div className="mt-6 flex gap-4 justify-center">
                  <Button
                    onClick={goNext}
                    className="bg-linear-to-r from-amber-600 to-orange-600 hover:from-amber-700 hover:to-orange-700 text-white px-8 py-3 text-lg"
                  >
                    <Play className="w-5 h-5 mr-2" />
                    Begin Story
                  </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Character + dialogue */}
        <AnimatePresence mode="wait">
          {currentData && (
            <motion.div
              key={currentTurn}
              initial={{ opacity: 0, x: -50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 50 }}
              transition={{ duration: 0.5 }}
              className="absolute top-20 md:top-24 bottom-0 left-0 right-0 flex items-end justify-between p-4 md:p-8 z-10"
            >
              {/* Phase 3-C: character nameplate moved below image */}
              <motion.div
                initial={{ y: 100, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.2, duration: 0.5 }}
                className="flex flex-col items-center"
              >
                <CharacterPicture
                  large
                  image={charByKey[currentData.character]?.image}
                  name={currentData.speaker}
                  color={charByKey[currentData.character]?.color}
                  className="h-48 md:h-72 object-contain drop-shadow-2xl"
                />
                <div className={`mt-1 px-3 py-0.5 rounded-full bg-linear-to-r ${colorsOf(currentData.character).bg} text-white text-xs font-semibold shadow-lg whitespace-nowrap`}>
                  {currentData.speaker}
                </div>
              </motion.div>

              <AnimatePresence>
                {showDialogue && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8, y: 20 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ duration: 0.4 }}
                    className="flex-1 self-stretch min-h-0 flex flex-col justify-end ml-4 md:ml-8 mb-8"
                  >
                    {/* Phase 2-A: palette bubble + Phase 3-A: typewriter */}
                    {/* max-h-full + scrolling body: long lines must not grow over the title */}
                    <div
                      className="relative max-w-xl max-h-full flex flex-col rounded-2xl overflow-hidden shadow-2xl"
                      onClick={skipTyping}
                      style={{ cursor: isTyping ? 'pointer' : 'default' }}
                    >
                      {/* Character name header */}
                      <div className={`shrink-0 px-4 py-2 bg-linear-to-r ${colorsOf(currentData.character).bg} flex items-center justify-between`}>
                        <span className="text-white text-xs font-bold uppercase tracking-wider drop-shadow">
                          {currentData.speaker}
                        </span>
                        {/* Phase 3-B: TTS waveform state */}
                        <button
                          onClick={e => { e.stopPropagation(); isSpeaking ? stopAudio() : speakTurn(currentData); }}
                          disabled={isTTSLoading}
                          className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium transition-all
                            ${isSpeaking ? 'bg-white/40 text-white' : 'bg-white/20 text-white hover:bg-white/30'}
                            disabled:opacity-40`}
                        >
                          {isTTSLoading ? (
                            <Volume2 className="w-3 h-3 animate-spin" />
                          ) : isSpeaking ? (
                            <><WaveformIcon /><Square className="w-2.5 h-2.5 ml-0.5" /></>
                          ) : (
                            <><Volume2 className="w-3 h-3" /><span>Listen</span></>
                          )}
                        </button>
                      </div>
                      {/* Dialogue body */}
                      <div
                        ref={dialogueBodyRef}
                        className={`${colorsOf(currentData.character).bubble} border-2 border-t-0 rounded-b-2xl p-4 md:p-5 min-h-0 overflow-y-auto`}
                      >
                        <p className={`text-sm md:text-base leading-relaxed ${colorsOf(currentData.character).text} min-h-[2em]`}>
                          {displayedText.split('\n').map((line, i, arr) => (
                            <span key={i}>
                              {line}
                              {i < arr.length - 1 && <><br /><br /></>}
                            </span>
                          ))}
                          {isTyping && (
                            <span style={{ display: 'inline-block', width: '2px', height: '1em', background: 'currentColor', marginLeft: '2px', verticalAlign: 'middle', animation: 'blink 0.7s step-end infinite' }} />
                          )}
                        </p>
                        {!isTyping && currentData.actionText && (
                          <p className="mt-2 text-xs italic opacity-70">{currentData.actionText}</p>
                        )}
                        {isTyping && (
                          <p className="mt-2 text-xs opacity-40">tap to skip</p>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Conclusion */}
        <AnimatePresence>
          {isConclusion && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 flex items-center justify-center p-6 z-20"
            >
              <div className="bg-black/70 backdrop-blur-md rounded-2xl max-w-3xl w-full shadow-2xl border border-amber-500/30 overflow-hidden">
                <div className="bg-linear-to-r from-amber-600/80 to-orange-600/80 px-8 py-4 text-center">
                  <p className="text-amber-100 text-xs font-bold uppercase tracking-[0.2em]">The story ends</p>
                  <h2 className="text-2xl md:text-3xl font-bold text-white mt-1">
                    {storyData?.title ?? "The Rickshaw Accident"}
                  </h2>
                </div>
                <div className="p-8">
                  {storyData?.conclusion ? (
                    <p className="text-gray-200 text-base md:text-lg leading-relaxed italic text-center">
                      {storyData.conclusion}
                    </p>
                  ) : (
                    <p className="text-gray-400 text-base italic text-center">
                      The streets of Karachi fell quiet as the story drew to a close.
                    </p>
                  )}
                  <div className="mt-8 flex justify-center">
                    <Button
                      onClick={restart}
                      className="bg-linear-to-r from-amber-600 to-orange-600 hover:from-amber-700 hover:to-orange-700 text-white px-8 py-3"
                    >
                      <RotateCcw className="w-5 h-5 mr-2" />
                      Watch Again
                    </Button>
                    <Button
                      onClick={backToMenu}
                      className="ml-3 bg-white/10 hover:bg-white/20 text-white px-8 py-3"
                    >
                      <HomeIcon className="w-5 h-5 mr-2" />
                      Menu
                    </Button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Director narration (clamped) ── */}
      {currentData && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="bg-gray-950 text-white px-4 py-3 md:px-6 border-t border-white/10"
        >
          <div className="flex items-start gap-3">
            <div className="bg-amber-500 text-black text-xs font-bold px-2 py-1 rounded uppercase tracking-wider shrink-0 mt-0.5">
              Director
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-gray-300 text-sm leading-relaxed italic ${!isNarrationExpanded ? 'line-clamp-2' : ''}`}>
                {currentData.narration}
              </p>
              {currentData.narration && currentData.narration.length > 120 && (
                <button
                  onClick={() => setIsNarrationExpanded(prev => !prev)}
                  className="text-amber-400 text-xs mt-1 hover:text-amber-300 transition-colors"
                >
                  {isNarrationExpanded ? '▲ Show less' : '▼ Read more'}
                </button>
              )}
            </div>
            {/* Phase 3-B: TTS waveform in director bar */}
            {currentData.narration && (
              <button
                onClick={() => isSpeaking ? stopAudio() : speakTurn({ dialogue: currentData.narration, character: 'director' })}
                disabled={isTTSLoading}
                className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium shrink-0 transition-all
                  ${isSpeaking ? 'bg-amber-500 text-black' : 'bg-white/10 text-gray-300 hover:bg-white/20'}
                  disabled:opacity-40`}
              >
                {isSpeaking ? <WaveformIcon /> : <Volume2 className="w-3 h-3" />}
              </button>
            )}
          </div>
        </motion.div>
      )}

      {/* Phase 3-B: Progress bar with glow */}
      {storyData && (
        <div className="bg-gray-900 h-1.5 overflow-hidden">
          <motion.div
            className="h-full bg-linear-to-r from-amber-500 to-orange-500 shadow-[0_0_8px_rgba(251,146,60,0.6)]"
            initial={{ width: 0 }}
            animate={{ width: `${((currentTurn + 2) / (totalTurns + 2)) * 100}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      )}

      {/* Navigation */}
      {storyData && (
        <div className="bg-gray-950 px-4 py-3 flex items-center justify-between border-t border-white/10">
          <Button
            onClick={goPrev}
            disabled={currentTurn <= -1}
            variant="ghost"
            className="text-white hover:bg-white/10 disabled:opacity-30 px-2"
          >
            <ChevronLeft className="w-5 h-5" />
            <span className="hidden md:inline ml-1 text-sm">Prev</span>
          </Button>

          <div className="flex items-center gap-3">
            {totalTurns > 0 && (
              <div className="flex items-center gap-1">
                {Array.from({ length: Math.min(totalTurns, 16) }).map((_, i) => (
                  <div
                    key={i}
                    className={`rounded-full transition-all duration-300 ${
                      i < currentTurn + 1
                        ? 'w-2 h-2 bg-amber-400'
                        : i === currentTurn + 1
                        ? 'w-2 h-2 bg-amber-400/50'
                        : 'w-1.5 h-1.5 bg-white/20'
                    }`}
                  />
                ))}
              </div>
            )}
            <span className="text-white/40 text-xs tabular-nums">
              {currentTurn === -1 ? 'Intro' : isConclusion ? 'End' : `${currentTurn + 1}/${totalTurns}`}
            </span>
            {!isConclusion && currentTurn >= 0 && (
              <button
                onClick={toggleAutoPlay}
                className={`p-1.5 rounded-lg transition-colors ${isAutoPlaying ? 'text-amber-400 bg-amber-400/10' : 'text-white/50 hover:text-white hover:bg-white/10'}`}
              >
                {isAutoPlaying ? <Volume2 className="w-4 h-4 animate-pulse" /> : <Play className="w-4 h-4" />}
              </button>
            )}
            <button
              onClick={restart}
              aria-label="Restart" title="Restart"
              className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={backToMenu}
              aria-label="Menu" title="Menu (Continue / New / Purani stories)"
              className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors"
            >
              <HomeIcon className="w-4 h-4" />
            </button>
          </div>

          <Button
            onClick={goNext}
            disabled={isNextDisabled}
            variant="ghost"
            className="text-white hover:bg-white/10 disabled:opacity-30 px-2"
          >
            <span className="hidden md:inline mr-1 text-sm">Next</span>
            <ChevronRight className="w-5 h-5" />
          </Button>
        </div>
      )}

      {/* Character cards */}
      {storyData && (
        <div className="bg-gray-950 px-4 pb-4 pt-2 grid grid-cols-2 md:grid-cols-4 gap-3 border-t border-white/10">
          {characters.map(({ key, label: name, image }) => (
            <div
              key={key}
              className={`flex items-center gap-3 rounded-xl p-3 border transition-colors ${
                currentData?.character === key
                  ? 'bg-amber-500/10 border-amber-500/50'
                  : 'bg-white/5 border-white/10'
              }`}
            >
              <div className="w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-gray-800 flex items-center justify-center">
                <CharacterPicture
                  image={image}
                  name={name}
                  color={charByKey[key]?.color}
                  className="w-full h-full object-contain object-center"
                />
              </div>
              <span className={`text-xs md:text-sm font-medium ${
                currentData?.character === key ? 'text-amber-300' : 'text-gray-400'
              }`}>
                {name}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
