import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, Play, RotateCcw, Volume2, Square } from 'lucide-react';
import { Button } from './components/button';
import './App.css';

const characterImages = {
  saleem: "img4.png",
  raza: "img10.png",
  ahmed: "img3.png",
  jameel: "img9.png"
};

const sceneBackgrounds = {
  main: "img12.png",
};

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

const characterColors = {
  saleem:  { bg: "from-amber-500 to-orange-600", text: "text-amber-900", bubble: "bg-amber-50 border-amber-300" },
  ahmed:   { bg: "from-blue-600 to-indigo-700",  text: "text-blue-900",  bubble: "bg-blue-50 border-blue-300" },
  raza:    { bg: "from-slate-500 to-slate-700",  text: "text-slate-900", bubble: "bg-slate-50 border-slate-300" },
  jameel:  { bg: "from-emerald-500 to-teal-600", text: "text-emerald-900", bubble: "bg-emerald-50 border-emerald-300" }
};

const characterNames = {
  saleem: "Saleem (Rickshaw Driver)",
  ahmed:  "Ahmed Malik (BMW Driver)",
  raza:   "Constable Raza",
  jameel: "Uncle Jameel (Tea Vendor)"
};

const characterVoices = {
  saleem: "Saleem",
  ahmed:  "Ahmed Malik",
  raza:   "Constable Raza",
  jameel: "Uncle Jameel",
};

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
  const audioRef = useRef(null);
  const isAutoPlayingRef = useRef(false);

  const totalTurns = storyData?.turns?.length ?? 0;

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/story`, { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          if (data?.turns?.length) {
            setStoryData(data);
            setCurrentTurn(-1);
          }
        }
      } catch (_) {}
    })();
    return () => controller.abort();
  }, []);

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

  const skipTyping = () => {
    if (isTyping && currentData?.dialogue) {
      clearTimeout(typingTimerRef.current);
      setDisplayedText(currentData.dialogue);
      setIsTyping(false);
    }
  };

  const startStory = () => {
    setIsLoading(true);
    setRunError(null);
    const url = `${API_BASE}/api/run/stream?lang=${language}`;
    const es = new EventSource(url);
    let story = { title: null, scenario: null, turns: [], conclusion: "" };
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "meta") {
          story = { title: data.title, scenario: data.scenario, turns: [], conclusion: "" };
          setStoryData({ ...story });
        } else if (data.type === "turns" && Array.isArray(data.newTurns)) {
          const prevLen = story.turns.length;
          story.turns = [...story.turns, ...data.newTurns];
          setStoryData({ ...story });
          setCurrentTurn((prev) => (prev === prevLen - 1 && prev >= 0 ? story.turns.length - 1 : prev));
        } else if (data.type === "conclusion") {
          story.conclusion = data.conclusion ?? "";
          setStoryData({ ...story });
        } else if (data.type === "done") {
          es.close();
          setCurrentTurn(-1);
          setIsLoading(false);
        }
      } catch (_) {}
    };
    es.onerror = () => {
      es.close();
      setIsLoading(false);
      setRunError("Connection lost or server error. Please try again.");
    };
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
    const speaker = characterVoices[turn.character] || "";
    setIsTTSLoading(true);
    let blobUrl = null;
    try {
      const res = await fetch(
        `${API_BASE}/api/tts?text=${encodeURIComponent(text)}&speaker=${encodeURIComponent(speaker)}`
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

      {/* ── Full-bleed scene ── */}
      <div className="relative overflow-hidden flex-1" style={{ minHeight: 'calc(100vh - 260px)' }}>
        <img
          src={sceneBackgrounds.main}
          alt="Scene"
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-linear-to-t from-black/80 via-black/10 to-black/50" />

        {/* Title overlay */}
        <div className="absolute top-0 left-0 right-0 z-10 px-6 pt-5 pb-10 bg-linear-to-b from-black/70 to-transparent pointer-events-none">
          <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight drop-shadow-lg">
            {storyData?.title ?? "The Rickshaw Accident"}
          </h1>
          <p className="text-amber-300/80 text-sm mt-0.5">Shahrah-e-Faisal, Karachi</p>
        </div>

        {/* Start Story */}
        <AnimatePresence>
          {(!storyData || (storyData.turns?.length === 0 && !isLoading)) && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 flex items-center justify-center p-6 z-20"
            >
              <div className="bg-black/60 backdrop-blur-md rounded-2xl p-8 max-w-2xl w-full shadow-2xl border border-white/10">
                <h2 className="text-3xl font-bold text-amber-300 mb-4">Start Story</h2>
                <p className="text-gray-200 text-lg leading-relaxed mb-4">
                  Run the full narrative once. This may take a few minutes.
                </p>

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
                    {isLoading ? "Running story..." : "Start story"}
                  </Button>
                </div>
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
              className="absolute bottom-0 left-0 right-0 flex items-end justify-between p-4 md:p-8 z-10"
            >
              {/* Phase 3-C: character nameplate moved below image */}
              <motion.div
                initial={{ y: 100, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.2, duration: 0.5 }}
                className="flex flex-col items-center"
              >
                <img
                  src={characterImages[currentData.character]}
                  alt={currentData.speaker}
                  className="h-48 md:h-72 object-contain drop-shadow-2xl"
                />
                <div className={`mt-1 px-3 py-0.5 rounded-full bg-linear-to-r ${characterColors[currentData.character].bg} text-white text-xs font-semibold shadow-lg whitespace-nowrap`}>
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
                    className="flex-1 ml-4 md:ml-8 mb-8"
                  >
                    {/* Phase 2-A: palette bubble + Phase 3-A: typewriter */}
                    <div
                      className="relative max-w-xl rounded-2xl overflow-hidden shadow-2xl"
                      onClick={skipTyping}
                      style={{ cursor: isTyping ? 'pointer' : 'default' }}
                    >
                      {/* Character name header */}
                      <div className={`px-4 py-2 bg-linear-to-r ${characterColors[currentData.character].bg} flex items-center justify-between`}>
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
                      <div className={`${characterColors[currentData.character].bubble} border-2 border-t-0 rounded-b-2xl p-4 md:p-5`}>
                        <p className={`text-sm md:text-base leading-relaxed ${characterColors[currentData.character].text} min-h-[2em]`}>
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
              className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
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
          {Object.entries(characterNames).map(([key, name]) => (
            <div
              key={key}
              className={`flex items-center gap-3 rounded-xl p-3 border transition-colors ${
                currentData?.character === key
                  ? 'bg-amber-500/10 border-amber-500/50'
                  : 'bg-white/5 border-white/10'
              }`}
            >
              <div className="w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-gray-800 flex items-center justify-center">
                <img
                  src={characterImages[key]}
                  alt={name}
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
