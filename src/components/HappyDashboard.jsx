import React, { useRef, useEffect, useState, useCallback } from 'react';
import TopAudioBar from './TopAudioBar';
import '../dashboard.css';

/* ── Inline SVG Icons ──────────────────────────────────── */
const Ico = ({ d, size = 17 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);
const D = {
  power:    'M18.36 6.64a9 9 0 1 1-12.73 0M12 2v10',
  mic:      'M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8',
  micOff:   'M1 1l22 22M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23M12 19v4M8 23h8',
  cam:      'M23 7l-7 5 7 5V7zM1 5h15a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H1z',
  camOff:   'M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2m5.66 0H14a2 2 0 0 1 2 2v3.34l1 1L23 7v10M1 1l22 22',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
  hand:     'M18 11V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2M14 10V4a2 2 0 0 0-2-2 2 2 0 0 0-2 2v2M10 10.5V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2v8M6 14v-1a2 2 0 0 0-2-2 2 2 0 0 0-2 2v2a8 8 0 0 0 8 8h2a8 8 0 0 0 8-8v-1a2 2 0 0 0-2-2 2 2 0 0 0-2 2',
  globe:    'M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0zM3.6 9h16.8M3.6 15h16.8M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18',
  minus:    'M5 12h14',
  max:      'M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3',
  close:    'M18 6L6 18M6 6l12 12',
  clock:    'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 6v6l4 2',
  send:     'M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z',
};

/* ── SVG Connection + Data Flow Layer ──────────────────── */
function ConnectionLayer({ leftRef, rightRef, centerRef }) {
  const svgRef = useRef(null);
  const [paths, setPaths] = useState({ left: '', right1: '', right2: '', right3: '' });
  const animsRef = useRef([]);

  const computePaths = useCallback(() => {
    const svg = svgRef.current;
    if (!svg || !centerRef.current) return;
    const svgRect = svg.getBoundingClientRect();
    const cx = svgRect.width * 0.5;
    const cy = svgRect.height * 0.5;

    // Left panel right edge → center
    if (leftRef.current) {
      const lr = leftRef.current.getBoundingClientRect();
      const lx = lr.right - svgRect.left;
      const ly = lr.top + lr.height * 0.5 - svgRect.top;
      const midX = (lx + cx) / 2;
      setPaths(p => ({
        ...p,
        left: `M${lx},${ly} C${midX},${ly} ${midX},${cy} ${cx - 105},${cy}`
      }));
    }

    // Right modules left edge → center
    const rightCards = rightRef.current?.querySelectorAll('.hd-stat-card');
    if (rightCards && rightCards.length >= 3) {
      ['right1', 'right2', 'right3'].forEach((key, i) => {
        const card = rightCards[i];
        if (!card) return;
        const cr = card.getBoundingClientRect();
        const rx = cr.left - svgRect.left;
        const ry = cr.top + cr.height * 0.5 - svgRect.top;
        const midX = (rx + cx) / 2;
        setPaths(p => ({
          ...p,
          [key]: `M${cx + 105},${cy} C${midX},${cy} ${midX},${ry} ${rx},${ry}`
        }));
      });
    }
  }, [leftRef, rightRef, centerRef]);

  useEffect(() => {
    const t = setTimeout(computePaths, 120);
    window.addEventListener('resize', computePaths);
    return () => { clearTimeout(t); window.removeEventListener('resize', computePaths); };
  }, [computePaths]);

  return (
    <svg
      ref={svgRef}
      className="hd-connections"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 2, pointerEvents: 'none' }}
    >
      <defs>
        <linearGradient id="lg-left" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#00e5ff" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#00e5ff" stopOpacity="0.05" />
        </linearGradient>
        <linearGradient id="lg-right" x1="100%" y1="0%" x2="0%" y2="0%">
          <stop offset="0%" stopColor="#00e5ff" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#00e5ff" stopOpacity="0.05" />
        </linearGradient>
        {/* Glow filter */}
        <filter id="glow">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* Left connection */}
      {paths.left && (
        <>
          <path d={paths.left} stroke="url(#lg-left)" strokeWidth="0.8" fill="none" opacity="0.6" />
          <path d={paths.left} stroke="#00e5ff" strokeWidth="0.4" fill="none" opacity="0.4" filter="url(#glow)" />
          {/* Animated dots */}
          {[0, 1, 2].map(i => (
            <circle key={i} r="2" fill="#00e5ff" filter="url(#glow)" opacity="0.8">
              <animateMotion
                dur={`${2.5 + i * 0.8}s`}
                begin={`${i * 0.9}s`}
                repeatCount="indefinite"
                path={paths.left}
              />
              <animate attributeName="opacity" values="0;0.9;0.9;0" dur={`${2.5 + i * 0.8}s`} begin={`${i * 0.9}s`} repeatCount="indefinite" />
            </circle>
          ))}
        </>
      )}

      {/* Right connections */}
      {['right1', 'right2', 'right3'].map((key, i) => paths[key] && (
        <React.Fragment key={key}>
          <path d={paths[key]} stroke="url(#lg-right)" strokeWidth="0.8" fill="none" opacity="0.55" />
          <path d={paths[key]} stroke="#00e5ff" strokeWidth="0.4" fill="none" opacity="0.35" filter="url(#glow)" />
          {[0, 1].map(j => (
            <circle key={j} r="1.8" fill="#00e5ff" filter="url(#glow)" opacity="0.75">
              <animateMotion
                dur={`${2.2 + i * 0.5 + j * 0.7}s`}
                begin={`${i * 0.6 + j * 1.1}s`}
                repeatCount="indefinite"
                path={paths[key]}
              />
              <animate
                attributeName="opacity"
                values="0;0.85;0.85;0"
                dur={`${2.2 + i * 0.5 + j * 0.7}s`}
                begin={`${i * 0.6 + j * 1.1}s`}
                repeatCount="indefinite"
              />
            </circle>
          ))}
        </React.Fragment>
      ))}
    </svg>
  );
}

/* ── Blinking Background Nodes ─────────────────────────── */
const BG_NODES = [
  { top: '18%', left: '22%', nd: '3.2s', delay: '0s' },
  { top: '35%', left: '78%', nd: '4.1s', delay: '1.2s' },
  { top: '65%', left: '15%', nd: '2.8s', delay: '0.5s' },
  { top: '72%', left: '85%', nd: '3.7s', delay: '1.8s' },
  { top: '25%', left: '58%', nd: '5.0s', delay: '2.1s' },
  { top: '80%', left: '42%', nd: '3.4s', delay: '0.9s' },
  { top: '14%', left: '44%', nd: '4.5s', delay: '1.5s' },
  { top: '55%', left: '88%', nd: '2.9s', delay: '2.4s' },
];

/* ── Mini Waveform ─────────────────────────────────────── */
function MiniWave({ n = 12 }) {
  return (
    <div className="hd-wave">
      {Array.from({ length: n }, (_, i) => {
        const h = 4 + Math.random() * 12;
        const d = (0.5 + Math.random() * 0.9).toFixed(2) + 's';
        return (
          <div key={i} className="hd-wave-bar"
            style={{ '--wd': d, '--wh': `${h}px`, animationDelay: `${(i * 0.06).toFixed(2)}s` }} />
        );
      })}
    </div>
  );
}

/* ── Pulse Ring ────────────────────────────────────────── */
function PulseRing({ type = 'core', label }) {
  const r = 20, circ = 2 * Math.PI * r;
  return (
    <div className="hd-pulse-ring">
      <svg width="46" height="46" viewBox="0 0 46 46">
        <circle className="hd-ring-track" cx="23" cy="23" r={r} />
        <circle className={`hd-ring-fill ${type === 'task' ? 'task' : type === 'wave' ? 'wave' : ''}`}
          cx="23" cy="23" r={r} strokeDasharray={circ} strokeDashoffset={circ * 0.3} />
      </svg>
      <div className={`hd-ring-lbl ${type}`}>{label}</div>
    </div>
  );
}

/* ── Command Log ───────────────────────────────────────── */
function CommandLog({ messages, inputValue, setInputValue, handleSend }) {
  const bottomRef = useRef(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  const onKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  return (
    <div className="hd-glass">
      <div className="hd-plabel"><span className="dot" />COMMAND LOG</div>
      <div className="hd-logs">
        {messages.map((m, i) => {
          const isH = m.sender?.toLowerCase() === 'happy' || m.sender?.toLowerCase() === 'ada';
          const isU = m.sender?.toLowerCase() === 'user';
          return (
            <div key={i} className="hd-entry">
              <div className="hd-ets">[{m.time}]</div>
              <span className={`hd-esnd ${isH ? 'happy' : isU ? 'user' : 'sys'}`}>
                {isH ? 'HAPPY' : m.sender?.toUpperCase() || 'SYS'}
              </span>
              <div className="hd-etxt">{m.text}</div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
      <div className="hd-inp-row">
        <input
          className="hd-inp"
          placeholder="Enter command..."
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={onKey}
        />
        <button className="hd-send" onClick={handleSend}>
          <Ico d={D.send} size={12} />
        </button>
      </div>
    </div>
  );
}

/* ── HAPPY Core Orb ────────────────────────────────────── */
function HappyCore({ isConnected, audioAmp }) {
  return (
    <div className="hd-core-wrap">
      {/* Ambient halo */}
      <div className="hd-core-halo"
        style={{ transform: `scale(${1 + audioAmp * 0.5})`, transition: 'transform 0.1s' }} />

      {/* Orbit rings */}
      <div className="hd-orb-ring hd-orb-ring-1">
        <div className="hd-orbit-dot hd-orbit-dot-1" />
        <div className="hd-orbit-dot hd-orbit-dot-2" />
      </div>
      <div className="hd-orb-ring hd-orb-ring-2">
        <div className="hd-orbit-dot hd-orbit-dot-3" />
      </div>
      <div className="hd-orb-ring hd-orb-ring-3" />

      {/* Core circle */}
      <div className="hd-core"
        style={{
          animationPlayState: isConnected ? 'running' : 'paused',
          opacity: isConnected ? 1 : 0.38,
        }}
      >
        <div className="hd-core-txt">HAPPY</div>
        <div className="hd-core-indicator">
          <div className="hd-core-dot"
            style={{ background: isConnected ? undefined : '#ef4444', boxShadow: isConnected ? undefined : '0 0 8px #ef4444' }} />
          <span className="hd-core-state">{isConnected ? 'ONLINE' : 'OFFLINE'}</span>
        </div>
      </div>
    </div>
  );
}

/* ── 3 Floating Status Modules ─────────────────────────── */
function StatusModules({ isConnected, currentProject, lastActiveTime }) {
  // Format the real last-active timestamp; never show the live clock here
  const lastStr = lastActiveTime
    ? lastActiveTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : 'NEVER';
  return (
    <>
      {/* AI Status */}
      <div className="hd-stat-card">
        <div className="hd-stat-info">
          <div className="hd-stat-key">AI CORE STATUS</div>
          <div className={`hd-stat-val ${isConnected ? 'online' : ''}`}>
            {isConnected ? 'ONLINE' : 'OFFLINE'}
          </div>
        </div>
        <PulseRing type="core" label="●" />
      </div>

      {/* Active Task */}
      <div className="hd-stat-card">
        <div className="hd-stat-info">
          <div className="hd-stat-key">ACTIVE TASK</div>
          <div className="hd-stat-val" style={{ fontSize: 11 }}>
            {currentProject?.toUpperCase() || 'IDLE'}
          </div>
        </div>
        <PulseRing type="task" label={
          <span style={{ fontSize: 7 }}>{currentProject?.slice(0, 4).toUpperCase() || 'IDLE'}</span>
        } />
      </div>

      {/* Last Activity */}
      <div className="hd-stat-card">
        <div className="hd-stat-info">
          <div className="hd-stat-key">LAST ACTIVE</div>
          <MiniWave n={14} />
        </div>
        <PulseRing type="wave" label={
          <span style={{ fontSize: 7, color: 'rgba(16,185,129,0.7)' }}>{lastStr}</span>
        } />
      </div>
    </>
  );
}

/* ── Control Dock ──────────────────────────────────────── */
function Dock({
  isConnected, isMuted, isVideoOn, isHandTrackingEnabled, showSettings, showBrowserWindow,
  onTogglePower, onToggleMute, onToggleVideo, onToggleSettings, onToggleHand, onToggleBrowser,
}) {
  return (
    <div className="hd-dock">
      <div className="hd-dock-inner">
        <button className={`hd-btn power ${isConnected ? 'is-active' : ''}`} onClick={onTogglePower} data-tip="POWER">
          <Ico d={D.power} />
        </button>
        <div className="hd-sep" />
        <button className={`hd-btn mic ${!isMuted ? 'is-active' : ''}`} onClick={onToggleMute} data-tip={isMuted ? 'MIC OFF' : 'MIC ON'}>
          <Ico d={isMuted ? D.micOff : D.mic} />
        </button>
        <button className={`hd-btn ${isVideoOn ? 'is-active' : ''}`} onClick={onToggleVideo} data-tip="CAMERA">
          <Ico d={isVideoOn ? D.cam : D.camOff} />
        </button>
        <div className="hd-sep" />
        <button className={`hd-btn ${isHandTrackingEnabled ? 'is-active' : ''}`} onClick={onToggleHand} data-tip="GESTURES">
          <Ico d={D.hand} />
        </button>
        <button className={`hd-btn ${showBrowserWindow ? 'is-active' : ''}`} onClick={onToggleBrowser} data-tip="BROWSER">
          <Ico d={D.globe} />
        </button>
        <div className="hd-sep" />
        <button className={`hd-btn ${showSettings ? 'is-active' : ''}`} onClick={onToggleSettings} data-tip="SETTINGS">
          <Ico d={D.settings} />
        </button>
      </div>
    </div>
  );
}

/* ── Top Bar ───────────────────────────────────────────── */
function TopBar({ micAudioData, currentTime, fps, isVideoOn, onMinimize, onMaximize, onClose }) {
  const t = currentTime?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) || '--:--';
  return (
    <div className="hd-topbar">
      <div className="hd-topbar-left">
        <span className="hd-logo">HAPPY</span>
        <span className="hd-badge">V2.0.0</span>
        {isVideoOn && <span className="hd-badge" style={{ color: '#00e5ff', borderColor: 'rgba(0,229,255,0.4)' }}>FPS {fps}</span>}
      </div>
      <div className="hd-topbar-center">
        <TopAudioBar audioData={micAudioData} />
      </div>
      <div className="hd-topbar-right">
        <div className="hd-time">
          <Ico d={D.clock} size={10} />
          {t}
        </div>
        <button className="hd-win-btn" onClick={onMinimize}><Ico d={D.minus} size={10} /></button>
        <button className="hd-win-btn" onClick={onMaximize}><Ico d={D.max} size={10} /></button>
        <button className="hd-win-btn close" onClick={onClose}><Ico d={D.close} size={10} /></button>
      </div>
    </div>
  );
}

/* ── Main Dashboard ────────────────────────────────────── */
function HappyDashboard({
  isConnected, isMuted, isVideoOn, isHandTrackingEnabled,
  showSettings, showBrowserWindow, showCadWindow,
  messages, inputValue, setInputValue, handleSend,
  currentProject, currentTime, lastActiveTime, fps,
  aiAudioData, micAudioData, isModularMode,
  onTogglePower, onToggleMute, onToggleVideo,
  onToggleSettings, onToggleHand, onToggleBrowser,
  onMinimize, onMaximize, onClose,
  children,
}) {
  const audioAmp = aiAudioData
    ? aiAudioData.reduce((a, b) => a + b, 0) / aiAudioData.length / 255
    : 0;

  const leftRef   = useRef(null);
  const rightRef  = useRef(null);
  const centerRef = useRef(null);

  return (
    <div className="happy-dashboard">

      {/* ── Ambient Background ── */}
      <div className="hd-bg">
        <div className="hd-bg-grid" />
        <div className="hd-bg-scan" />
        <div className="hd-bg-glow" />
        {BG_NODES.map((n, i) => (
          <div key={i} className="hd-node"
            style={{ top: n.top, left: n.left, '--nd': n.nd, animationDelay: n.delay }} />
        ))}
      </div>

      {/* ── SVG Connection Lines (rendered inside center grid area, spans all) ── */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none', gridArea: 'unset' }}>
        <ConnectionLayer leftRef={leftRef} rightRef={rightRef} centerRef={centerRef} />
      </div>

      {/* ── Top Bar ── */}
      <TopBar
        micAudioData={micAudioData}
        currentTime={currentTime}
        fps={fps}
        isVideoOn={isVideoOn}
        onMinimize={onMinimize}
        onMaximize={onMaximize}
        onClose={onClose}
      />

      {/* ── Left Panel ── */}
      <div className="hd-left" ref={leftRef}>
        <CommandLog
          messages={messages}
          inputValue={inputValue}
          setInputValue={setInputValue}
          handleSend={handleSend}
        />
      </div>

      {/* ── Center ── */}
      <div className="hd-center" ref={centerRef}>
        {/* HUD corners */}
        <div className="hd-hud-corner tl" />
        <div className="hd-hud-corner tr" />
        <div className="hd-hud-corner bl" />
        <div className="hd-hud-corner br" />

        <div className="hd-proj-label">
          PROJECT: {currentProject?.toUpperCase() || 'TEMP'}
        </div>

        <HappyCore isConnected={isConnected} audioAmp={audioAmp} />
      </div>

      {/* ── Right Floating Modules ── */}
      <div className="hd-right" ref={rightRef}>
        <StatusModules
          isConnected={isConnected}
          currentProject={currentProject}
          lastActiveTime={lastActiveTime}
        />
      </div>

      {/* ── Control Dock ── */}
      <Dock
        isConnected={isConnected}
        isMuted={isMuted}
        isVideoOn={isVideoOn}
        isHandTrackingEnabled={isHandTrackingEnabled}
        showSettings={showSettings}
        showBrowserWindow={showBrowserWindow}
        onTogglePower={onTogglePower}
        onToggleMute={onToggleMute}
        onToggleVideo={onToggleVideo}
        onToggleSettings={onToggleSettings}
        onToggleHand={onToggleHand}
        onToggleBrowser={onToggleBrowser}
      />

      {/* ── Overlay Children ── */}
      {children}
    </div>
  );
}

export default HappyDashboard;
