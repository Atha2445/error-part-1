import React, { useState, useEffect, useMemo, useCallback, createContext } from 'react';
import { Home, Video, FileText, Settings, Bell, Upload, Download, Trash2, RefreshCw, BarChart3, Activity, ShieldOff, Lock, LogOut, User, Eye, EyeOff, Shield, Plus, X, Check, Edit2, Key, Send, ChevronDown, ChevronUp, FolderUp, TrendingUp, ShieldAlert, Sparkles, CheckCircle2, Terminal } from 'lucide-react';

const API_BASE = window.location.origin;

// ── Shared UI primitives ─────────────────────────────────────────────
// Each page gets its own accent colour so views feel distinct and scannable.
const ACCENTS = {
  blue:   { gradient: 'from-blue-500 to-indigo-600',     shadow: 'shadow-blue-500/30',   chip: 'bg-blue-100 text-blue-600',   card: 'border-blue-100',   text: 'text-blue-600' },
  violet: { gradient: 'from-violet-500 to-purple-600',   shadow: 'shadow-violet-500/30', chip: 'bg-violet-100 text-violet-600', card: 'border-violet-100', text: 'text-violet-600' },
  red:    { gradient: 'from-rose-500 to-red-600',        shadow: 'shadow-rose-500/30',   chip: 'bg-rose-100 text-rose-600',   card: 'border-rose-100',   text: 'text-rose-600' },
  teal:   { gradient: 'from-teal-500 to-emerald-600',    shadow: 'shadow-teal-500/30',   chip: 'bg-teal-100 text-teal-600',   card: 'border-teal-100',   text: 'text-teal-600' },
  purple: { gradient: 'from-fuchsia-500 to-purple-600',  shadow: 'shadow-fuchsia-500/30', chip: 'bg-fuchsia-100 text-fuchsia-600', card: 'border-fuchsia-100', text: 'text-fuchsia-600' },
  cyan:   { gradient: 'from-cyan-500 to-blue-600',       shadow: 'shadow-cyan-500/30',   chip: 'bg-cyan-100 text-cyan-600',   card: 'border-cyan-100',   text: 'text-cyan-600' },
  slate:  { gradient: 'from-slate-500 to-slate-700',     shadow: 'shadow-slate-500/30',  chip: 'bg-slate-100 text-slate-600', card: 'border-slate-200',  text: 'text-slate-600' },
  amber:  { gradient: 'from-amber-500 to-orange-600',    shadow: 'shadow-amber-500/30',  chip: 'bg-amber-100 text-amber-600', card: 'border-amber-100',  text: 'text-amber-600' },
};

const PageHeader = ({ icon: Icon, title, subtitle, accent = ACCENTS.blue, actions }) => (
  <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
    <div className="flex items-center gap-4">
      <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${accent.gradient} flex items-center justify-center text-white shadow-lg ${accent.shadow} flex-shrink-0`}>
        <Icon size={22} />
      </div>
      <div className="min-w-0">
        <h2 className="text-2xl md:text-3xl font-bold text-gray-800">{title}</h2>
        {subtitle && <div className="text-sm text-gray-500 mt-0.5">{subtitle}</div>}
      </div>
    </div>
    {actions && <div className="flex gap-2 flex-wrap">{actions}</div>}
  </div>
);

const StatCard = ({ label, value, icon: Icon, accent = ACCENTS.blue, className = '' }) => (
  <div className={`bg-white p-5 rounded-xl border ${accent.card} shadow-sm hover:shadow-md transition-shadow ${className}`}>
    <div className="flex items-center justify-between">
      <div className="min-w-0">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide truncate">{label}</p>
        <p className="text-2xl md:text-3xl font-bold text-gray-800 mt-1">{value}</p>
      </div>
      <div className={`w-11 h-11 rounded-lg ${accent.chip} flex items-center justify-center flex-shrink-0`}>
        <Icon size={22} />
      </div>
    </div>
  </div>
);

// ── Form primitives ──────────────────────────────────────────────────
const INPUT_CLS = 'w-full px-3.5 py-2.5 rounded-xl border border-gray-200 bg-gray-50/60 focus:bg-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all';
const TEXTAREA_CLS = 'w-full px-3.5 py-2.5 rounded-xl border border-gray-200 bg-gray-50/60 focus:bg-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all font-mono';

const Field = ({ label, hint, children }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
    {children}
    {hint && <p className="text-xs text-gray-400 mt-1.5">{hint}</p>}
  </div>
);

const SettingsCard = ({ icon: Icon, title, subtitle, children }) => (
  <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
    <div className="flex items-center gap-3 mb-5">
      <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center">
        <Icon size={18} />
      </div>
      <div>
        <h3 className="font-semibold text-gray-800">{title}</h3>
        {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
      </div>
    </div>
    {children}
  </div>
);

const ChipInput = ({ value, onChange, placeholder = 'Type and press Enter', chipCls = 'bg-blue-50 text-blue-700 border-blue-200' }) => {
  const [draft, setDraft] = useState('');
  const items = (value || '').split(',').map(s => s.trim()).filter(Boolean);

  const commit = () => {
    const next = draft.trim();
    if (!next) return;
    if (!items.some(i => i.toLowerCase() === next.toLowerCase())) {
      onChange([...items, next].join(', '));
    }
    setDraft('');
  };

  const remove = (target) => {
    onChange(items.filter(i => i !== target).join(', '));
  };

  return (
    <div className="w-full min-h-[46px] px-2.5 py-2 rounded-xl border border-gray-200 bg-gray-50/60 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-transparent text-sm transition-all flex flex-wrap items-center gap-1.5">
      {items.map(item => (
        <span key={item} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium ${chipCls}`}>
          {item}
          <button
            type="button"
            onClick={() => remove(item)}
            className="hover:text-red-600 transition-colors"
            title="Remove"
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); commit(); }
          else if (e.key === 'Backspace' && !draft && items.length) { remove(items[items.length - 1]); }
        }}
        onBlur={commit}
        placeholder={items.length === 0 ? placeholder : ''}
        className="flex-1 min-w-[140px] bg-transparent outline-none placeholder-gray-400"
      />
    </div>
  );
};



// ── Helper: Clean Human Narrative Sanitizer ─────────────────────────
const cleanSummaryText = (raw, fallbackContext = {}) => {
  if (!raw) raw = '';
  if (typeof raw === 'object' && raw !== null) {
    raw = raw.what_happened || raw.narrative_summary || raw.description || '';
  }
  if (typeof raw === 'string' && raw.trim().startsWith('{')) {
    try {
      const parsed = JSON.parse(raw);
      raw = parsed.human_summary?.what_happened || parsed.narrative_summary || parsed.what_happened || parsed.description || '';
    } catch (e) {}
  }
  if (typeof raw !== 'string') raw = String(raw || '');

  // Strip closed and unclosed thinking tags
  let cleaned = raw
    .replace(/[◁<]think[▷>].*?[◁<]\/think[▷>]/gs, '')
    .replace(/[◁<]think[▷>].*/gs, '')
    .replace(/[◁<]\/think[▷>]/gs, '')
    .replace(/^[#\s]*```(json)?/gi, '')
    .replace(/```[#\s]*$/gi, '')
    .trim();

  // If contaminated by timestamp listing, too short, or still contains JSON / think tokens
  const isJunk = (
    !cleaned ||
    cleaned.length < 20 ||
    cleaned.includes('◁think▷') ||
    cleaned.includes('<think>') ||
    /00:\d\d,\s*00:\d\d/.test(cleaned) ||
    /\d:\d\d\s*-\s*\d:\d\d:\s*Routine/.test(cleaned) ||
    (cleaned.startsWith('{') && cleaned.endsWith('}'))
  );

  if (!isJunk) {
    return cleaned;
  }

  // Fallback to high-quality plain English 2-3 sentence summary
  const incident = fallbackContext.final_incident || fallbackContext.incidentType || '';
  const risk = fallbackContext.risk_level || fallbackContext.risk || '';
  const rec = fallbackContext.recommendation || 'Standard operational protocols apply.';

  if (incident === 'ANIMAL_ASSAULT' || (risk && risk.includes('Animal'))) {
    return `Surveillance initially recorded routine activity in the area. An active animal assault (dog attack) was identified and confirmed by vision models. ${rec}`;
  } else if (incident === 'SMOKE_WARNING') {
    return `Surveillance footage showed smoke that kept growing or rising, without visible flames. This can be an early-stage fire. ${rec}`;
  } else if (incident === 'FIRE_SMOKE' || (risk && risk.includes('Fire'))) {
    return `Surveillance footage initially captured normal conditions in the monitored area. An active fire and smoke hazard was identified and verified by vision models. ${rec}`;
  } else if (incident === 'WEAPON' || (risk && risk.includes('Weapon'))) {
    return `Surveillance recording initially shows routine baseline activity. A visible weapon (firearm/knife) was detected and confirmed by security vision models. ${rec}`;
  } else if (incident === 'FIGHT_ASSAULT' || (risk && risk.includes('Fight'))) {
    return `Surveillance initially recorded normal interactions in the area. A physical altercation between individuals was identified by security vision models. ${rec}`;
  } else if (incident === 'ROUTINE_ANIMAL') {
    return 'Surveillance footage shows peaceful routine activity. A non-aggressive animal was observed passing through the monitored zone with no safety risk.';
  } else {
    return 'Surveillance recording proceeded normally with no physical threats, weapons, or safety hazards detected. Normal operational baseline confirmed.';
  }
};

// ── Auth Context ────────────────────────────────────────────────────
const AuthContext = createContext(null);

function getStoredToken() {
  return localStorage.getItem('vigilinx_token');
}

function getStoredUser() {
  try {
    const raw = localStorage.getItem('vigilinx_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function authFetch(url, options = {}) {
  const token = getStoredToken();
  const headers = { ...(options.headers || {}) };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return fetch(url, { ...options, headers });
}

// Pick the first page the user has permission to see, in priority order.
// Returns null if the user has no permissions at all.
const PAGE_PRIORITY = ['dashboard', 'analytics', 'analyze', 'detections', 'verdicts', 'cctv', 'prompts', 'settings', 'admin'];
function getDefaultView(permissions) {
  const perms = permissions || [];
  for (const key of PAGE_PRIORITY) {
    if (perms.includes(key)) return key;
  }
  return null;
}

// ── Login Page ──────────────────────────────────────────────────────
const LoginPage = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Login failed');
      }

      const data = await response.json();
      localStorage.setItem('vigilinx_token', data.token);
      localStorage.setItem('vigilinx_user', JSON.stringify(data.user));
      onLogin(data.token, data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-blue-500/20 mb-4">
            <Lock className="text-blue-400" size={36} />
          </div>
          <h1 className="text-3xl font-bold text-white mb-1">Vigilinx</h1>
          <p className="text-blue-200/60 text-sm">Sign in to your account</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-white/10 backdrop-blur-lg rounded-2xl border border-white/20 p-8 shadow-2xl"
        >
          {error && (
            <div className="mb-5 p-3 bg-red-500/20 border border-red-400/30 rounded-lg text-red-200 text-sm text-center">
              {error}
            </div>
          )}

          <div className="mb-5">
            <label className="block text-sm font-medium text-blue-100 mb-2">Username</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 text-blue-300/50" size={18} />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-blue-300/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                placeholder="Enter your username"
                autoFocus
                autoComplete="username"
              />
            </div>
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-blue-100 mb-2">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-blue-300/50" size={18} />
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-12 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-blue-300/40 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                placeholder="Enter your password"
                autoComplete="current-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-blue-300/50 hover:text-blue-200 transition-colors"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <RefreshCw size={18} className="animate-spin" />
                Signing in...
              </>
            ) : (
              'Sign In'
            )}
          </button>

          <p className="text-center text-xs text-blue-200/30 mt-6">
            Default credentials: admin / admin
          </p>
        </form>

        <p className="text-center text-xs text-blue-200/20 mt-6">
          Vigilinx &mdash; iTechSeed
        </p>
      </div>
    </div>
  );
};

// Sidebar Component
const ALL_MENU_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: Home },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'analyze', label: 'Video Analysis', icon: Video },
  { id: 'detections', label: 'Detection Logs', icon: FileText },
  { id: 'prompts', label: 'Manage Prompts', icon: Settings },
  { id: 'verdicts', label: 'Video Verdicts', icon: Activity },
  { id: 'cctv', label: 'Manage CCTV', icon: Eye },
  { id: 'settings', label: 'System Settings', icon: Settings },
  { id: 'admin', label: 'Admin Panel', icon: Shield },
];

const Sidebar = ({ currentView, setCurrentView, isWatchdogRunning, user, onLogout }) => {
  const userPermissions = user?.permissions || [];
  const visibleItems = ALL_MENU_ITEMS.filter(item => userPermissions.includes(item.id));
  const pageAccents = {
    dashboard: 'blue', analytics: 'violet', analyze: 'teal', detections: 'red', prompts: 'purple',
    verdicts: 'amber', cctv: 'cyan', settings: 'slate', admin: 'amber',
  };

  return (
    <div className="w-64 bg-gradient-to-b from-[#14294a] to-[#1e3a5f] h-screen text-white flex flex-col flex-shrink-0">
      <div className="p-6 border-b border-white/10">
        <div className="w-full h-20 bg-white/10 flex items-center justify-center mb-4 rounded-xl overflow-hidden ring-1 ring-white/10">
          <img src="/logo.jpeg" alt="iTechSeed Logo" className="w-full h-full object-contain" />
        </div>
        <h1 className="text-xl font-bold tracking-tight">Vigilinx</h1>
        <p className="text-xs text-gray-400 mt-0.5">iTechSeed · Security Monitor</p>

        <div className="flex items-center gap-2 mt-4 px-2.5 py-1.5 rounded-lg bg-white/10 w-fit">
          <div className={`w-2 h-2 rounded-full ${isWatchdogRunning ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`}></div>
          <span className="text-[10px] uppercase font-bold tracking-wider text-gray-100">
            {isWatchdogRunning ? 'Scanning' : 'Offline'}
          </span>
        </div>
      </div>

      <nav className="flex-1 p-4 overflow-y-auto">
        <p className="text-[10px] uppercase font-bold tracking-widest text-gray-500 px-3 mb-3">Monitor</p>
        {visibleItems.map(item => {
          const Icon = item.icon;
          const active = currentView === item.id;
          const accent = ACCENTS[pageAccents[item.id]] || ACCENTS.blue;
          return (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              className={`relative w-full flex items-center gap-3 pl-4 pr-3 py-3 rounded-lg mb-1.5 transition-all ${
                active
                  ? 'bg-white/10 text-white shadow-inner'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {active && (
                <span className={`absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-r ${accent.gradient}`} />
              )}
              <Icon size={20} className={active ? accent.text : ''} />
              <span className="text-sm font-medium">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="p-4 border-t border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`w-9 h-9 bg-gradient-to-br ${ACCENTS.blue.gradient} rounded-full flex items-center justify-center flex-shrink-0`}>
              <span className="text-sm font-bold text-white">{(user?.display_name || user?.username || 'U')[0].toUpperCase()}</span>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{user?.display_name || user?.username || 'User'}</p>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-400 truncate">@{user?.username || 'user'}</span>
              </div>
            </div>
          </div>
          <button
            onClick={onLogout}
            className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex-shrink-0"
            title="Sign Out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};

// Dashboard View
// Dashboard View
const Dashboard = ({ isWatchdogRunning, setCurrentView }) => {
  const [stats, setStats] = useState({
    totalVideos: 0,
    suspiciousDetections: 0,
    normalFrames: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardStats();
  }, []);

  const fetchDashboardStats = async () => {
    setLoading(true);
    try {
      const response = await authFetch(`${API_BASE}/api/dashboard/stats`);
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Error fetching dashboard stats:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={Home}
        title="Dashboard Overview"
        subtitle="System status and recent activity at a glance"
        accent={ACCENTS.blue}
        actions={
          <button
            onClick={fetchDashboardStats}
            className="px-4 py-2 bg-white text-gray-700 rounded-lg border border-gray-200 hover:border-blue-300 hover:text-blue-600 flex items-center gap-2 shadow-sm transition-colors"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <StatCard
          label="System Status"
          value={loading ? '...' : (isWatchdogRunning ? 'Active Scanning' : 'Monitor Offline')}
          icon={Activity}
          accent={isWatchdogRunning ? ACCENTS.blue : ACCENTS.red}
          className="col-span-2 lg:col-span-1"
        />
        <StatCard label="Total Analyzed" value={loading ? '...' : stats.totalVideos} icon={Video} accent={ACCENTS.blue} />
        <StatCard label="Suspicious Detections" value={loading ? '...' : stats.suspiciousDetections} icon={Bell} accent={ACCENTS.red} />
        <StatCard label="Normal Videos" value={loading ? '...' : stats.normalFrames} icon={Shield} accent={ACCENTS.teal} />
        <StatCard label="Avg Occupancy" value={loading ? '...' : (stats.avgOccupancy || 0)} icon={BarChart3} accent={ACCENTS.purple} />
      </div>

      <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${isWatchdogRunning ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
          Quick Actions
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div
            onClick={() => setCurrentView('analyze')}
            className="p-5 border-2 border-dashed border-gray-300 rounded-xl text-center cursor-pointer hover:border-violet-400 hover:bg-violet-50/50 hover:shadow-sm transition-all"
          >
            <div className="mx-auto mb-3 w-12 h-12 rounded-xl bg-violet-100 text-violet-600 flex items-center justify-center">
              <Upload size={24} />
            </div>
            <p className="text-sm font-medium text-gray-700">Live Video Analysis</p>
            <p className="text-xs text-gray-400 mt-0.5">Automatically analyze new videos</p>
          </div>
          <div
            onClick={() => setCurrentView('detections')}
            className="p-5 border-2 border-dashed border-gray-300 rounded-xl text-center cursor-pointer hover:border-rose-400 hover:bg-rose-50/50 hover:shadow-sm transition-all"
          >
            <div className="mx-auto mb-3 w-12 h-12 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center">
              <FileText size={24} />
            </div>
            <p className="text-sm font-medium text-gray-700">Detection Summary</p>
            <p className="text-xs text-gray-400 mt-0.5">Review detections and download logs</p>
          </div>
          <div
            onClick={() => {
              sessionStorage.setItem('vigilinx_open_upload', 'true');
              setCurrentView('analyze');
            }}
            className="p-5 border-2 border-dashed border-gray-300 rounded-xl text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/50 hover:shadow-sm transition-all"
          >
            <div className="mx-auto mb-3 w-12 h-12 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center">
              <FolderUp size={24} />
            </div>
            <p className="text-sm font-medium text-gray-700">Upload Dataset</p>
            <p className="text-xs text-gray-400 mt-0.5">Upload surveillance footage & clips</p>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Analytics & Intelligence Dashboard View ────────────────────────
const Analytics = ({ setCurrentView }) => {
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [kpis, setKpis] = useState({
    total_videos: 0,
    threat_incidents: 0,
    clear_videos: 0,
    threat_rate_pct: 0,
    avg_occupancy: 0,
    vlm_accuracy_index: null,
  });
  const [trends, setTrends] = useState([]);
  const [breakdown, setBreakdown] = useState({
    weapons: 0,
    fights: 0,
    fire_smoke: 0,
    animals: 0,
    clear: 0,
  });
  const [occupancyHourly, setOccupancyHourly] = useState([]);
  const [recentVerdicts, setRecentVerdicts] = useState([]);
  const [hoveredTrend, setHoveredTrend] = useState(null);
  const [summarizingId, setSummarizingId] = useState(null);

  const fetchAnalytics = useCallback(async (selectedDays) => {
    setLoading(true);
    try {
      const [kpiRes, trendRes, breakRes, occRes, verdRes] = await Promise.all([
        authFetch(`${API_BASE}/api/analytics/kpis`),
        authFetch(`${API_BASE}/api/analytics/threat-trends?days=${selectedDays}`),
        authFetch(`${API_BASE}/api/analytics/threat-breakdown`),
        authFetch(`${API_BASE}/api/analytics/occupancy-hourly`),
        authFetch(`${API_BASE}/api/verdicts`),
      ]);

      if (kpiRes.ok) setKpis(await kpiRes.json());
      if (trendRes.ok) setTrends(await trendRes.json());
      if (breakRes.ok) setBreakdown(await breakRes.json());
      if (occRes.ok) setOccupancyHourly(await occRes.json());
      if (verdRes.ok) {
        const vData = await verdRes.json();
        setRecentVerdicts(Array.isArray(vData) ? vData.slice(0, 6) : []);
      }
    } catch (err) {
      console.error('Error fetching analytics data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAnalytics(days);
  }, [days, fetchAnalytics]);

  const handleExportCSV = async () => {
    setExporting(true);
    try {
      const res = await authFetch(`${API_BASE}/api/analytics/export-csv`);
      if (!res.ok) throw new Error('Failed to export CSV');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vigilinx_surveillance_report_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Error exporting CSV report: ' + err.message);
    } finally {
      setExporting(false);
    }
  };

  const handleRunSummarize = async (verdictId) => {
    setSummarizingId(verdictId);
    try {
      const res = await authFetch(`${API_BASE}/api/video/summarize/${verdictId}`, {
        method: 'POST',
      });
      if (res.ok) {
        const sumData = await res.json();
        setRecentVerdicts(prev =>
          prev.map(v =>
            v.id === verdictId
              ? { ...v, ai_summary: sumData.narrative_summary || JSON.stringify(sumData) }
              : v
          )
        );
      }
    } catch (err) {
      console.error('Failed to generate summary:', err);
    } finally {
      setSummarizingId(null);
    }
  };

  const totalThreatDetections = (breakdown.weapons || 0) + (breakdown.fights || 0) + (breakdown.fire_smoke || 0) + (breakdown.animals || 0);

  const maxTrendTotal = useMemo(() => {
    if (!trends || trends.length === 0) return 5;
    return Math.max(...trends.map(t => t.total || 0), 5);
  }, [trends]);

  const maxOccupancy = useMemo(() => {
    if (!occupancyHourly || occupancyHourly.length === 0) return 5;
    return Math.max(...occupancyHourly.map(o => o.peak_people || o.avg_people || 0), 5);
  }, [occupancyHourly]);

  return (
    <div className="p-8 space-y-8">
      <PageHeader
        icon={BarChart3}
        title="Surveillance Analytics & Intelligence"
        subtitle="Multi-threat detection telemetry, VLM forensic narratives & operational metrics"
        accent={ACCENTS.violet}
        actions={
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center bg-white border border-gray-200 rounded-lg p-1 shadow-sm">
              {[7, 14, 30, 90].map(d => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                    days === d
                      ? 'bg-violet-600 text-white shadow-sm'
                      : 'text-gray-600 hover:text-violet-600'
                  }`}
                >
                  {d} Days
                </button>
              ))}
            </div>

            <button
              onClick={() => fetchAnalytics(days)}
              disabled={loading}
              className="px-3.5 py-2 bg-white text-gray-700 rounded-lg border border-gray-200 hover:border-violet-300 hover:text-violet-600 flex items-center gap-2 shadow-sm text-sm transition-colors"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin text-violet-600' : ''} />
              Refresh
            </button>

            <button
              onClick={handleExportCSV}
              disabled={exporting}
              className="px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-700 hover:to-indigo-700 text-white rounded-lg shadow-sm text-sm font-medium flex items-center gap-2 transition-all"
            >
              <Download size={16} className={exporting ? 'animate-bounce' : ''} />
              {exporting ? 'Exporting...' : 'Export CSV Report'}
            </button>
          </div>
        }
      />

      {/* Top Level Metric KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Total Scans"
          value={loading ? '...' : kpis.total_videos}
          icon={Video}
          accent={ACCENTS.blue}
        />
        <StatCard
          label="Threat Incidents"
          value={loading ? '...' : `${kpis.threat_incidents} (${kpis.threat_rate_pct}%)`}
          icon={Bell}
          accent={ACCENTS.red}
        />
        <StatCard
          label="Verified Clean"
          value={loading ? '...' : kpis.clear_videos}
          icon={Shield}
          accent={ACCENTS.teal}
        />
        <StatCard
          label="Average Crowd"
          value={loading ? '...' : `${kpis.avg_occupancy} ppl`}
          icon={BarChart3}
          accent={ACCENTS.purple}
        />
        <StatCard
          label="AI Accuracy"
          value={loading ? '...' : (kpis.vlm_accuracy_index == null ? 'Not measured' : `${kpis.vlm_accuracy_index}%`)}
          icon={Sparkles}
          accent={ACCENTS.violet}
          className="col-span-2 lg:col-span-1"
        />
      </div>

      {/* Threat Distribution Across 4 Modules */}
      <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <ShieldAlert className="text-rose-600" size={20} />
              Threat Distribution & Intelligence Classification
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Verified signals across Guns/Knives, Fights, Fire/Smoke, and Animal Attacks
            </p>
          </div>
          <span className="text-xs font-semibold px-3 py-1 bg-rose-50 text-rose-700 border border-rose-200 rounded-full">
            {totalThreatDetections} Total Flagged Detections
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Weapons */}
          <div className="p-4 rounded-xl border border-rose-100 bg-gradient-to-br from-rose-50/60 to-red-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-rose-700 uppercase tracking-wide">Weapons & Blades</span>
              <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-rose-200/60 text-rose-800">CRITICAL</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{breakdown.weapons || 0}</p>
            <p className="text-xs text-gray-500 mt-0.5">Guns, Knives, Grenades</p>
            <div className="w-full bg-rose-200/50 rounded-full h-1.5 mt-3">
              <div
                className="bg-rose-600 h-1.5 rounded-full transition-all duration-500"
                style={{
                  width: `${totalThreatDetections ? Math.round(((breakdown.weapons || 0) / totalThreatDetections) * 100) : 0}%`,
                }}
              />
            </div>
          </div>

          {/* Fights */}
          <div className="p-4 rounded-xl border border-orange-100 bg-gradient-to-br from-orange-50/60 to-amber-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-orange-700 uppercase tracking-wide">Fights & Assault</span>
              <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-orange-200/60 text-orange-800">CRITICAL</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{breakdown.fights || 0}</p>
            <p className="text-xs text-gray-500 mt-0.5">Pose Dynamics & Rapid Arms</p>
            <div className="w-full bg-orange-200/50 rounded-full h-1.5 mt-3">
              <div
                className="bg-orange-600 h-1.5 rounded-full transition-all duration-500"
                style={{
                  width: `${totalThreatDetections ? Math.round(((breakdown.fights || 0) / totalThreatDetections) * 100) : 0}%`,
                }}
              />
            </div>
          </div>

          {/* Fire & Smoke */}
          <div className="p-4 rounded-xl border border-amber-100 bg-gradient-to-br from-amber-50/60 to-yellow-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-amber-700 uppercase tracking-wide">Fire & Smoke</span>
              <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-amber-200/60 text-amber-800">HIGH / CRIT</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{breakdown.fire_smoke || 0}</p>
            <p className="text-xs text-gray-500 mt-0.5">Early Smoke & Active Flames</p>
            <div className="w-full bg-amber-200/50 rounded-full h-1.5 mt-3">
              <div
                className="bg-amber-600 h-1.5 rounded-full transition-all duration-500"
                style={{
                  width: `${totalThreatDetections ? Math.round(((breakdown.fire_smoke || 0) / totalThreatDetections) * 100) : 0}%`,
                }}
              />
            </div>
          </div>

          {/* Animals */}
          <div className="p-4 rounded-xl border border-purple-100 bg-gradient-to-br from-purple-50/60 to-violet-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-purple-700 uppercase tracking-wide">Animal Hazards</span>
              <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-purple-200/60 text-purple-800">HIGH</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{breakdown.animals || 0}</p>
            <p className="text-xs text-gray-500 mt-0.5">Stray Dogs & Animal Encounters</p>
            <div className="w-full bg-purple-200/50 rounded-full h-1.5 mt-3">
              <div
                className="bg-purple-600 h-1.5 rounded-full transition-all duration-500"
                style={{
                  width: `${totalThreatDetections ? Math.round(((breakdown.animals || 0) / totalThreatDetections) * 100) : 0}%`,
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Daily Surveillance Incident Trends Chart */}
      <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <TrendingUp className="text-violet-600" size={20} />
              Surveillance Activity & Threat Timeline
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Daily volume comparing confirmed security incidents against routine baseline scans
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-rose-500"></span>
              <span className="text-gray-600 font-medium">Threat Incidents</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-emerald-500"></span>
              <span className="text-gray-600 font-medium">Routine / Clear</span>
            </div>
          </div>
        </div>

        {trends.length === 0 ? (
          <div className="py-16 text-center text-gray-400 border border-dashed border-gray-200 rounded-xl">
            <Video size={36} className="mx-auto text-gray-300 mb-2" />
            <p className="text-sm font-medium">No recorded surveillance activity in the last {days} days.</p>
            <p className="text-xs text-gray-400 mt-1">Upload or scan CCTV footage to populate the timeline.</p>
          </div>
        ) : (
          <div className="h-64 flex items-end gap-3 pt-6 pb-2 px-2 overflow-x-auto">
            {trends.map((t, idx) => {
              const threatHeight = maxTrendTotal ? (t.threats / maxTrendTotal) * 100 : 0;
              const clearHeight = maxTrendTotal ? (t.clear / maxTrendTotal) * 100 : 0;
              const isHovered = hoveredTrend === idx;

              return (
                <div
                  key={t.date}
                  onMouseEnter={() => setHoveredTrend(idx)}
                  onMouseLeave={() => setHoveredTrend(null)}
                  className="flex-1 min-w-[48px] flex flex-col items-center h-full justify-end group relative cursor-pointer"
                >
                  {/* Tooltip */}
                  {isHovered && (
                    <div className="absolute -top-14 bg-slate-900 text-white text-[11px] py-1.5 px-3 rounded-lg shadow-xl whitespace-nowrap z-20 pointer-events-none">
                      <p className="font-bold text-gray-200">{t.date}</p>
                      <p className="text-rose-400">Threats: {t.threats} (Critical: {t.critical})</p>
                      <p className="text-emerald-400">Clear: {t.clear}</p>
                    </div>
                  )}

                  {/* Stacked Bars */}
                  <div className="w-full max-w-[28px] flex flex-col justify-end h-full gap-1">
                    {t.threats > 0 && (
                      <div
                        style={{ height: `${Math.max(threatHeight, 8)}%` }}
                        className="w-full bg-rose-500 rounded-t-md shadow-sm transition-all group-hover:brightness-110"
                      />
                    )}
                    {t.clear > 0 && (
                      <div
                        style={{ height: `${Math.max(clearHeight, 8)}%` }}
                        className={`w-full bg-emerald-500 ${t.threats > 0 ? 'rounded-b-md' : 'rounded-md'} shadow-sm transition-all group-hover:brightness-110`}
                      />
                    )}
                  </div>

                  <span className="text-[10px] text-gray-500 font-medium mt-2 truncate w-full text-center">
                    {t.date.slice(5)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Hourly Facility Occupancy Curve */}
      <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <Activity className="text-indigo-600" size={20} />
              24-Hour Facility Traffic & Occupancy Pattern
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Average and peak human occupancy across time of day (00:00 - 23:00)
            </p>
          </div>
          <span className="text-xs text-gray-500 font-medium">Auto-aggregated from YOLO Detections</span>
        </div>

        {occupancyHourly.length === 0 ? (
          <div className="py-12 text-center text-gray-400">
            <p className="text-sm">No hourly human occupancy data logged yet.</p>
          </div>
        ) : (
          <div className="h-44 flex items-end gap-2 pt-6 pb-2 overflow-x-auto">
            {occupancyHourly.map((h, i) => {
              const height = maxOccupancy ? (h.avg_people / maxOccupancy) * 100 : 0;
              return (
                <div key={h.hour} className="flex-1 min-w-[32px] flex flex-col items-center h-full justify-end group relative">
                  <div className="absolute -top-8 hidden group-hover:block bg-slate-900 text-white text-[10px] py-1 px-2 rounded shadow whitespace-nowrap z-10">
                    {h.hour}: Avg {h.avg_people} ppl (Peak: {h.peak_people})
                  </div>
                  <div
                    style={{ height: `${Math.max(height, 6)}%` }}
                    className="w-full max-w-[18px] bg-indigo-500/80 hover:bg-indigo-600 rounded-t transition-all"
                  />
                  <span className="text-[9px] text-gray-400 mt-1">{h.hour.slice(0, 2)}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* VLM AI Forensic Narratives Feed */}
      <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <Sparkles className="text-violet-600" size={20} />
              VLM Narrative Summaries & AI Audits
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              AI narratives explaining sequences of events across surveillance recordings
            </p>
          </div>
          <button
            onClick={() => setCurrentView('verdicts')}
            className="text-xs font-semibold text-violet-600 hover:text-violet-700 flex items-center gap-1"
          >
            View All Verdicts &rarr;
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {recentVerdicts.map(v => {
            const hasSummary = Boolean(v.ai_summary && v.ai_summary !== 'N/A');
            const isThreat = Boolean(v.needs_attention);

            return (
              <div
                key={v.id}
                className={`p-5 rounded-xl border transition-all ${
                  isThreat ? 'border-rose-200 bg-rose-50/20' : 'border-gray-200 bg-gray-50/40'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-gray-800 truncate max-w-[220px]" title={v.video_path}>
                    {v.video_path}
                  </span>
                  <span
                    className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                      isThreat ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'
                    }`}
                  >
                    {v.risk_level || (isThreat ? 'THREAT' : 'NORMAL')}
                  </span>
                </div>

                <p className="text-xs text-gray-600 mb-3 line-clamp-3">
                  {hasSummary ? v.ai_summary : v.recommendation || 'Standard operations confirmed.'}
                </p>

                <div className="flex items-center justify-between text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                  <span>{v.timestamp || 'Recent'}</span>
                  <button
                    onClick={() => handleRunSummarize(v.id)}
                    disabled={summarizingId === v.id}
                    className="text-violet-600 font-semibold hover:text-violet-700 flex items-center gap-1"
                  >
                    {summarizingId === v.id ? (
                      <>
                        <RefreshCw size={12} className="animate-spin" />
                        Generating AI Narrative...
                      </>
                    ) : (
                      <>
                        <Sparkles size={12} />
                        {hasSummary ? 'Re-Analyze with VLM' : 'Generate AI Narrative'}
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};


// Video Analysis View
const STEPS = [
  { key: 'idle',      label: 'Ready' },
  { key: 'uploading', label: 'Uploading' },
  { key: 'preparing', label: 'Preparing' },
  { key: 'analyzing', label: 'Analyzing' },
  { key: 'finalizing',label: 'Finalizing' },
  { key: 'done',      label: 'Complete' },
];

const ProgressStepper = ({ stage, progress }) => {
  const activeIdx = STEPS.findIndex(s => s.key === stage);
  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        {STEPS.filter(s => s.key !== 'idle').map((step, i) => {
          const stepIdx = i + 1;
          const isActive = stepIdx === activeIdx;
          const isDone = stepIdx < activeIdx || stage === 'done';
          return (
            <div key={step.key} className="flex-1 flex flex-col items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all duration-300 ${
                isDone ? 'bg-green-500 border-green-500 text-white' :
                isActive ? 'bg-blue-500 border-blue-500 text-white animate-pulse' :
                'bg-white border-gray-300 text-gray-400'
              }`}>
                {isDone ? '✓' : stepIdx}
              </div>
              <span className={`text-xs mt-1 ${isActive ? 'text-blue-600 font-semibold' : isDone ? 'text-green-600' : 'text-gray-400'}`}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
      {(stage === 'analyzing' || stage === 'finalizing') && (
        <div className="w-full bg-gray-200 rounded-full h-2.5 mt-2">
          <div
            className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
      {stage === 'analyzing' && (
        <p className="text-sm text-gray-500 text-center mt-1">Analyzing... {progress}%</p>
      )}
    </div>
  );
};

const VideoAnalysis = () => {
  const [file, setFile] = useState(null);
  const [threshold, setThreshold] = useState(0.3);
  const [analyzeFullVideo, setAnalyzeFullVideo] = useState(false);
  const [maxDuration, setMaxDuration] = useState(300);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [stage, setStage] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [pollingRef] = useState({ current: null });
  const [watchStatus, setWatchStatus] = useState({ watch_dir: '', watchdog_running: false, tasks: [] });
  const [showUpload, setShowUpload] = useState(() => {
    const open = sessionStorage.getItem('vigilinx_open_upload');
    if (open === 'true') {
      sessionStorage.removeItem('vigilinx_open_upload');
    }
    return true; // Default to true so upload interface is always immediately accessible
  });

  useEffect(() => {
    let cancelled = false;
    const pollWatchStatus = async () => {
      try {
        const response = await authFetch(`${API_BASE}/api/watch/status`);
        if (!response.ok) return;
        const data = await response.json();
        if (!cancelled) setWatchStatus(data);
      } catch (err) {
        console.error('Error fetching watch status:', err);
      }
    };
    pollWatchStatus();
    const id = setInterval(pollWatchStatus, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const watchStats = useMemo(() => {
    const tasks = watchStatus.tasks || [];
    return {
      total: tasks.length,
      analyzing: tasks.filter(t => t.status === 'processing').length,
      alerts: tasks.filter(t => t.status === 'completed' &&
        (t.result?.risk_level?.includes('CRITICAL') || t.result?.risk_level?.includes('HIGH'))).length,
      completed: tasks.filter(t => t.status === 'completed').length,
    };
  }, [watchStatus.tasks]);

  const sortedTasks = useMemo(() => {
    const rank = t => t.status === 'processing' ? 0 : t.status === 'failed' ? 1 : 2;
    return [...(watchStatus.tasks || [])].sort(
      (a, b) => rank(a) - rank(b) || (b.timestamp || 0) - (a.timestamp || 0)
    );
  }, [watchStatus.tasks]);

  const isProcessing = !['idle', 'done'].includes(stage) && stage !== 'failed';

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setResult(null);
    setError(null);
    setStage('idle');
    setProgress(0);
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const resetAnalysis = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setStage('idle');
    setProgress(0);
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const analyzeVideo = async () => {
    if (!file) return;
    setResult(null);
    setError(null);
    setStage('uploading');
    setProgress(0);

    const formData = new FormData();
    formData.append('video', file);
    formData.append('suspicious_threshold', threshold);
    formData.append('analyze_full_video', analyzeFullVideo);
    formData.append('max_analysis_duration', maxDuration);

    try {
      const response = await authFetch(`${API_BASE}/api/video/analyze-async`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      setStage('preparing');
      pollStatus(data.task_id);
    } catch (err) {
      setError(err.message);
      setStage('idle');
    }
  };

  const pollStatus = (taskId) => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    pollingRef.current = setInterval(async () => {
      try {
        const response = await authFetch(`${API_BASE}/api/video/status/${taskId}`);
        const data = await response.json();

        if (data.stage) setStage(data.stage);
        if (typeof data.progress === 'number') setProgress(data.progress);

        if (data.status === 'completed') {
          setResult(data);
          setStage('done');
          setProgress(100);
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        } else if (data.status === 'failed') {
          setError(data.error || 'Video processing failed');
          setStage('idle');
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 2000);
  };

  const downloadVideo = async () => {
    downloadAnalyzed(result?.verdict?.video_id);
  };

  const downloadAnalyzed = async (videoId) => {
    if (!videoId) return;
    try {
      const response = await authFetch(`${API_BASE}/api/video/download/${videoId}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = videoId;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  const getStatusBadge = (task) => {
    if (task.status === 'completed') {
      const lvl = task.result?.verdict?.risk_level || task.result?.risk_level || '';
      const cls = lvl.includes('CRITICAL') || lvl.includes('HIGH')
        ? 'bg-red-100 text-red-700'
        : lvl.includes('MEDIUM')
          ? 'bg-yellow-100 text-yellow-700'
          : lvl.includes('LOW') || lvl.includes('CLEAR')
            ? 'bg-green-100 text-green-700'
            : 'bg-gray-100 text-gray-700';
      return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>{lvl || 'Completed'}</span>;
    }
    if (task.status === 'failed') {
      return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">Failed</span>;
    }
    return (
      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 animate-pulse">
        {task.stage === 'detected' ? 'Queued' : 'Analyzing...'}
      </span>
    );
  };

  const getRiskColor = (level) => {
    if (level?.includes('CRITICAL')) return 'bg-red-100 text-red-700 border-red-400';
    if (level?.includes('HIGH')) return 'bg-orange-100 text-orange-700 border-orange-400';
    if (level?.includes('MEDIUM')) return 'bg-yellow-100 text-yellow-700 border-yellow-300';
    if (level?.includes('LOW')) return 'bg-green-100 text-green-700 border-green-300';
    if (level?.includes('CLEAR')) return 'bg-emerald-100 text-emerald-700 border-emerald-300';
    return 'bg-gray-100 text-gray-700 border-gray-300';
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={Video}
        title="Live Monitoring"
        accent={ACCENTS.violet}
        subtitle={
          <div className="flex items-center flex-wrap gap-2">
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
              watchStatus.watchdog_running ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}>
              {watchStatus.watchdog_running ? '● Live' : '● Stopped'}
            </span>
            <span>
              Watching{' '}
              <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">{watchStatus.watch_dir || '—'}</code>
              <span className="text-gray-400"> · new video files here are analyzed automatically</span>
            </span>
          </div>
        }
        actions={
          <button
            onClick={() => setShowUpload(v => !v)}
            className={`px-4 py-2 rounded-lg border text-sm font-medium flex items-center gap-2 transition-colors ${
              showUpload
                ? 'border-gray-200 text-gray-600 bg-white hover:bg-gray-50'
                : 'border-violet-200 text-violet-600 bg-white hover:bg-violet-50'
            }`}
          >
            {showUpload ? <X size={16} /> : <Upload size={16} />}
            {showUpload ? 'Close' : 'Upload a file'}
          </button>
        }
      />

      {isProcessing && showUpload && <ProgressStepper stage={stage} progress={progress} />}

      {showUpload && (
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h3 className="text-xl font-semibold mb-4">Upload Video</h3>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">Select Video File</label>
            <input
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              disabled={isProcessing}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            />
            {file && (
              <div className="mt-2 p-3 bg-gray-50 rounded-lg text-sm text-gray-600 space-y-1">
                <p><span className="font-medium">File:</span> {file.name}</p>
                <p><span className="font-medium">Size:</span> {formatFileSize(file.size)}</p>
                {file.size > 100 * 1024 * 1024 && (
                  <p className="text-amber-600 text-xs font-medium">Large file — Quick scan (first 5 min) recommended for faster results.</p>
                )}
              </div>
            )}
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Suspicious Threshold: {Math.round(threshold * 100)}%
            </label>
            <input
              type="range" min="0" max="1" step="0.05" value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              disabled={isProcessing}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>More Sensitive</span>
              <span>Less Sensitive</span>
            </div>
          </div>

          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <label className="block text-sm font-medium text-gray-700 mb-2">Analysis Scope</label>
            <div className="space-y-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio" name="scope" checked={!analyzeFullVideo}
                  onChange={() => setAnalyzeFullVideo(false)} disabled={isProcessing}
                  className="text-blue-600"
                />
                <div>
                  <span className="text-sm text-gray-700 font-medium">Quick Scan (first {maxDuration / 60} min)</span>
                  <p className="text-xs text-gray-500">Faster results — recommended for most use cases</p>
                </div>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio" name="scope" checked={analyzeFullVideo}
                  onChange={() => setAnalyzeFullVideo(true)} disabled={isProcessing}
                  className="text-blue-600"
                />
                <div>
                  <span className="text-sm text-gray-700 font-medium">Full Video</span>
                  <p className="text-xs text-gray-500">Analyzes entire recording — may take longer for large files</p>
                </div>
              </label>
            </div>
            {!analyzeFullVideo && (
              <div className="mt-3">
                <label className="block text-xs font-medium text-gray-500 mb-1">
                  Max duration to analyze: {maxDuration / 60} min
                </label>
                <input
                  type="range" min="60" max="1800" step="60" value={maxDuration}
                  onChange={(e) => setMaxDuration(parseInt(e.target.value))}
                  disabled={isProcessing}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-400">
                  <span>1 min</span>
                  <span>30 min</span>
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            onClick={isProcessing ? undefined : (result ? resetAnalysis : analyzeVideo)}
            disabled={(!file && !result) || isProcessing}
            className={`w-full py-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-colors ${
              isProcessing
                ? 'bg-gray-400 text-white cursor-not-allowed'
                : result
                  ? 'bg-gray-600 text-white hover:bg-gray-700'
                  : 'bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed'
            }`}
          >
            {isProcessing ? (
              <>
                <RefreshCw size={20} className="animate-spin" />
                Processing...
              </>
            ) : result ? (
              'Analyze Another Video'
            ) : (
              <>
                <Upload size={20} />
                Analyze Video
              </>
            )}
          </button>
        </div>

        {result && (() => {
          const v = result.verdict || {};
          const isAnimalAssault = (v.animal_assaults_count || 0) > 0 || (v.risk_level || '').includes('Animal');
          const isFight = (v.fights_count || 0) > 0 && !isAnimalAssault;
          const isWeapon = (v.weapons_count || 0) > 0;
          const isFire = (v.fires_count || 0) > 0;
          const hasThreat = isAnimalAssault || isFight || isWeapon || isFire || (v.suspicious_frames || 0) > 0;
          const normalFrames = v.normal_frames || 0;
          const suspFrames = v.suspicious_frames || 0;
          const totalFrames = v.total_analyzed || 0;
          const dur = v.duration || 0;
          const incidentSec = dur > 3 ? Math.max(1, Math.round(dur * (normalFrames / (totalFrames || 1)))) : 0;
          const incidentTime = `${String(Math.floor(incidentSec / 60)).padStart(2, '0')}:${String(incidentSec % 60).padStart(2, '0')}`;
          const totalTime = `${String(Math.floor(dur / 60)).padStart(2, '0')}:${String(Math.round(dur % 60)).padStart(2, '0')}`;
          const threatLabel = isAnimalAssault ? 'ANIMAL ASSAULT (DOG ATTACK)' : isFight ? 'HUMAN ALTERCATION' : isWeapon ? 'WEAPON DETECTED' : isFire ? 'FIRE / SMOKE' : 'SUSPICIOUS ACTIVITY';
          const threatIcon = isAnimalAssault ? '🐕' : isFight ? '🥊' : isWeapon ? '🗡️' : isFire ? '🔥' : '⚠️';

          return (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            {/* === Incident Flagging Timeline Flow === */}
            <div className="p-5 border-b border-gray-100">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                  <ShieldAlert size={20} className="text-rose-500" />
                  Surveillance Analysis Report
                </h3>
                {hasThreat && (
                  <span className="px-3 py-1 rounded-full text-xs font-bold bg-red-100 text-red-700 border border-red-200 animate-pulse">
                    🚩 INCIDENT FLAGGED
                  </span>
                )}
              </div>

              {/* Temporal Baseline → Incident Flow */}
              <div className="space-y-3">
                {/* Normal Baseline */}
                <div className="flex items-start gap-3">
                  <div className="flex flex-col items-center">
                    <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center text-sm font-bold">🟢</div>
                    {hasThreat && <div className="w-0.5 h-8 bg-gray-200"></div>}
                  </div>
                  <div className="flex-1 py-1">
                    <p className="text-sm font-semibold text-emerald-700">00:00 — {hasThreat ? incidentTime : totalTime} Routine Normal</p>
                    <p className="text-xs text-gray-500 mt-0.5">Surveillance area was calm with normal activity. No threats detected during this baseline period.</p>
                  </div>
                </div>

                {/* Incident Trigger */}
                {hasThreat && (
                  <div className="flex items-start gap-3">
                    <div className="flex flex-col items-center">
                      <div className="w-8 h-8 rounded-full bg-red-100 text-red-600 flex items-center justify-center text-sm font-bold">🚩</div>
                      <div className="w-0.5 h-8 bg-gray-200"></div>
                    </div>
                    <div className="flex-1 py-1">
                      <p className="text-sm font-bold text-red-700">{incidentTime} INCIDENT FLAGGED: {threatLabel}</p>
                      <p className="text-xs text-gray-600 mt-0.5">
                        Sudden deviation from normal baseline detected! {threatIcon} {threatLabel} confirmed with{' '}
                        <span className="font-semibold text-red-600">{suspFrames}</span> suspicious frames across {totalFrames} analyzed.
                      </p>
                    </div>
                  </div>
                )}

                {/* Forensic Assessment */}
                <div className="flex items-start gap-3">
                  <div className="flex flex-col items-center">
                    <div className="w-8 h-8 rounded-full bg-violet-100 text-violet-600 flex items-center justify-center text-sm font-bold">📋</div>
                  </div>
                  <div className="flex-1 py-1">
                    <div className={`p-3 rounded-lg border-2 ${getRiskColor(v.risk_level)}`}>
                      <p className="font-bold text-sm">{v.risk_level}</p>
                      <p className="text-xs mt-1">{v.recommendation}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* === Detection Statistics Grid === */}
            <div className="p-5 border-b border-gray-100">
              <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
                {[
                  { label: 'Total Frames', value: totalFrames, color: 'text-gray-800' },
                  { label: 'Suspicious', value: suspFrames, color: suspFrames > 0 ? 'text-red-600' : 'text-gray-800' },
                  { label: 'Normal', value: normalFrames, color: 'text-emerald-600' },
                  { label: 'Animals', value: v.animals_count || 0, color: (v.animals_count || 0) > 0 ? 'text-amber-600' : 'text-gray-500' },
                  { label: 'Animal Assaults', value: v.animal_assaults_count || 0, color: (v.animal_assaults_count || 0) > 0 ? 'text-red-700' : 'text-gray-500' },
                  { label: 'Human Fights', value: v.fights_count || 0, color: (v.fights_count || 0) > 0 ? 'text-purple-700' : 'text-gray-500' },
                ].map(s => (
                  <div key={s.label} className="text-center p-2 bg-gray-50 rounded-lg">
                    <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wide">{s.label}</p>
                    <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
                  </div>
                ))}
              </div>

              {v.analysis_scope && (
                <p className="text-xs text-gray-400 mt-2 text-center">
                  Scope: {v.analysis_scope === 'full' ? 'Full video analyzed' : `Analyzed ${v.analysis_scope}`}
                </p>
              )}
            </div>

            {/* === Top Suspicious Activities with Threat Badges === */}
            {v.top_suspicious_activities?.length > 0 && (
              <div className="p-5 border-b border-gray-100">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Detected Threat Activities</h4>
                <div className="flex flex-wrap gap-2">
                  {v.top_suspicious_activities.map(([activity, count], idx) => {
                    const act = activity.toUpperCase();
                    const isAnimal = act.includes('ANIMAL') || act.includes('DOG');
                    const isFightAct = act.includes('FIGHT') || act.includes('ASSAULT');
                    const isWeaponAct = act.includes('WEAPON') || act.includes('GUN') || act.includes('KNIFE');
                    const isFireAct = act.includes('FIRE') || act.includes('SMOKE');
                    const badgeCls = isAnimal ? 'bg-amber-50 text-amber-800 border-amber-200'
                      : isFightAct ? 'bg-purple-50 text-purple-800 border-purple-200'
                      : isWeaponAct ? 'bg-red-50 text-red-800 border-red-200'
                      : isFireAct ? 'bg-orange-50 text-orange-800 border-orange-200'
                      : 'bg-rose-50 text-rose-700 border-rose-200';
                    const badgeIcon = isAnimal ? '🐕' : isFightAct ? '🥊' : isWeaponAct ? '🗡️' : isFireAct ? '🔥' : '⚠️';
                    return (
                      <span key={idx} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold ${badgeCls}`}>
                        <span>{badgeIcon}</span>
                        <span>{activity}</span>
                        <span className="font-bold">({count}×)</span>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* === AI Narrative Summary === */}
            {v.ai_summary && (
              <div className="p-5 border-b border-gray-100">
                <div className="p-4 bg-gradient-to-r from-violet-50/80 via-purple-50/50 to-indigo-50/60 border border-violet-200/80 rounded-xl">
                  <div className="flex items-center gap-2 mb-2">
                    <Sparkles size={14} className="text-violet-600" />
                    <span className="text-xs font-bold text-violet-800 uppercase tracking-wide">AI Summary</span>
                    <span className="ml-auto px-2 py-0.5 bg-violet-100 text-violet-700 rounded-full text-xs font-semibold">AI Native</span>
                  </div>
                  <p className="text-sm text-gray-800 leading-relaxed">
                    {typeof v.ai_summary === 'string' ? v.ai_summary
                      : v.ai_summary?.narrative_summary || JSON.stringify(v.ai_summary)}
                  </p>
                </div>
              </div>
            )}

            {/* === Embedded Video Player === */}
            {v.video_id && (
              <div className="p-5 border-b border-gray-100">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <Eye size={14} />
                  Surveillance Playback
                </h4>
                <video
                  controls
                  className="w-full rounded-lg border border-gray-200 bg-black max-h-[360px]"
                  src={`${API_BASE}/api/video/download/${v.video_id}`}
                >
                  Your browser does not support video playback.
                </video>
              </div>
            )}

            {/* === Alert Keyframe Evidence Gallery === */}
            {result.alert_keyframes?.length > 0 && (
              <div className="p-5 border-b border-gray-100">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">🚩 Alert Keyframe Evidence ({result.alert_keyframes.length})</h4>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  {result.alert_keyframes.slice(0, 8).map((kf, idx) => (
                    <div key={idx} className="relative rounded-lg overflow-hidden border border-red-200 shadow-sm">
                      <img
                        src={`data:image/jpeg;base64,${kf.b64}`}
                        alt={`Alert frame ${kf.frame_number}`}
                        className="w-full h-auto"
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                        <p className="text-[10px] text-white font-semibold">
                          Frame #{kf.frame_number} · {kf.timestamp_sec?.toFixed(1)}s · {kf.severity}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* === Download Button === */}
            <div className="p-5">
              <button
                onClick={downloadVideo}
                className="w-full bg-gradient-to-r from-emerald-600 to-green-600 text-white py-3 rounded-xl font-semibold hover:from-emerald-700 hover:to-green-700 flex items-center justify-center gap-2 shadow-md transition-all"
              >
                <Download size={20} />
                Download Analyzed Video
              </button>
            </div>
          </div>
          );
        })()}
      </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Files Detected', value: watchStats.total, cls: 'border-blue-200 bg-blue-50', valCls: 'text-blue-700' },
          { label: 'Analyzing Now', value: watchStats.analyzing, cls: 'border-indigo-200 bg-indigo-50', valCls: 'text-indigo-700' },
          { label: 'Alerts', value: watchStats.alerts, cls: 'border-red-200 bg-red-50', valCls: 'text-red-700' },
          { label: 'Completed', value: watchStats.completed, cls: 'border-green-200 bg-green-50', valCls: 'text-green-700' },
        ].map(s => (
          <div key={s.label} className={`rounded-xl border ${s.cls} p-4 hover:shadow-md transition-shadow`}>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{s.label}</p>
            <p className={`text-3xl font-bold ${s.valCls}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        {!sortedTasks.length ? (
          <div className="bg-white p-10 rounded-xl border-2 border-dashed border-gray-300 text-center">
            <FileText className="mx-auto mb-3 text-gray-300" size={40} />
            <p className="text-gray-600 font-medium">No videos detected yet</p>
            <p className="text-sm text-gray-400 mt-1">
              Drop a video file into <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">{watchStatus.watch_dir || 'the watch directory'}</code>{' '}
              and analysis will start automatically.
            </p>
          </div>
        ) : (
          sortedTasks.map(task => (
            <div key={task.filename} className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <FileText size={18} className="text-gray-400 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{task.filename}</p>
                    <p className="text-xs text-gray-400">{new Date(task.timestamp * 1000).toLocaleString()}</p>
                  </div>
                </div>
                {getStatusBadge(task)}
              </div>

              {task.status === 'failed' ? (
                <p className="text-xs text-red-600 mt-2">{task.error || 'Analysis failed'}</p>
              ) : task.status === 'processing' ? (
                <div className="mt-2">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${task.progress || 0}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{task.progress || 0}%</p>
                </div>
              ) : task.status === 'completed' && task.result ? (() => {
                const resData = task.result.verdict || task.result || {};
                const suspFrames = resData.suspicious_frames ?? 0;
                const totalFrames = resData.total_analyzed ?? resData.total_frames_scanned ?? 0;
                const suspPct = typeof resData.suspicious_percentage === 'number'
                  ? resData.suspicious_percentage.toFixed(1)
                  : totalFrames > 0
                    ? ((suspFrames / totalFrames) * 100).toFixed(1)
                    : '0.0';
                const vidId = task.result.video_id || resData.video_id;
                return (
                  <div className="flex items-center justify-between gap-2 mt-2">
                    <p className="text-sm text-gray-700">
                      Suspicious:{' '}
                      <span className={`font-semibold ${suspFrames > 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {suspFrames}
                      </span>{' '}
                      / {totalFrames} windows · {suspPct}%
                    </p>
                    {vidId && (
                      <button
                        onClick={() => downloadAnalyzed(vidId)}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                      >
                        <Download size={12} /> Download
                      </button>
                    )}
                  </div>
                );
              })() : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// Detection Logs View
const DetectionLogs = () => {
  const [logs, setLogs] = useState([]);
  const [verdicts, setVerdicts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedSummary, setExpandedSummary] = useState({});
  const [expandedEngLogs, setExpandedEngLogs] = useState({});
  const [summarizingId, setSummarizingId] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [detRes, verRes] = await Promise.all([
        authFetch(`${API_BASE}/api/detections`),
        authFetch(`${API_BASE}/api/verdicts`),
      ]);
      const detData = await detRes.json();
      const verData = await verRes.json();
      setLogs(detData || []);
      setVerdicts(verData.verdicts || []);
    } catch (error) {
      console.error('Error fetching detection data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRunSummarize = async (verdictId) => {
    setSummarizingId(verdictId);
    try {
      const res = await authFetch(`${API_BASE}/api/video/summarize/${verdictId}`, {
        method: 'POST',
      });
      if (res.ok) {
        const sumData = await res.json();
        const narrative = sumData.narrative_summary || JSON.stringify(sumData);
        setVerdicts(prev =>
          prev.map(v =>
            v.id === verdictId
              ? { ...v, ai_summary: narrative }
              : v
          )
        );
      }
    } catch (err) {
      console.error('Failed to summarize:', err);
    } finally {
      setSummarizingId(null);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const buildVideoSummary = (v) => {
    if (v.verdict?.ai_summary) {
      return v.verdict.ai_summary;
    }
    const sentences = [];
    const risk = v.verdict?.risk_level || '';
    const actions = (v.topSusp || []).map(([a]) => a);

    if (risk.includes('CRITICAL') || risk.includes('HIGH')) {
      sentences.push('A high-priority incident was detected in this video recording.');
    } else if (risk.includes('MEDIUM')) {
      sentences.push('Some suspicious activity was detected and flagged for review.');
    } else if (risk.includes('ROUTINE')) {
      sentences.push('Peaceful routine activity was observed in the surveillance area.');
    } else {
      sentences.push('This video shows normal operational activity with no security concerns.');
    }

    if (actions.length === 1) {
      sentences.push(`Primary activity: ${actions[0]}.`);
    } else if (actions.length > 1) {
      const last = actions[actions.length - 1];
      const rest = actions.slice(0, -1).join(', ');
      sentences.push(`Detected signals: ${rest}, and ${last}.`);
    }

    if (v.verdict?.recommendation) {
      sentences.push(v.verdict.recommendation);
    }
    return sentences.join(' ');
  };

  const summary = useMemo(() => {
    const byVideo = {};
    logs.forEach(l => {
      const name = l.video_path?.split(/[\\/]/).pop() || 'unknown';
      if (!byVideo[name]) byVideo[name] = { name, detections: 0, alerts: 0, actions: {}, suspActions: {} };
      byVideo[name].detections += 1;
      if (l.is_alert) byVideo[name].alerts += 1;
      if (l.detected_action) {
        byVideo[name].actions[l.detected_action] = (byVideo[name].actions[l.detected_action] || 0) + 1;
        if (l.is_alert) {
          byVideo[name].suspActions[l.detected_action] = (byVideo[name].suspActions[l.detected_action] || 0) + 1;
        }
      }
    });

    verdicts.forEach(vd => {
      const name = vd.video_path?.split(/[\\/]/).pop() || 'unknown';
      if (!byVideo[name]) {
        byVideo[name] = { name, detections: vd.total_analyzed || 0, alerts: vd.suspicious_frames || 0, actions: {}, suspActions: {} };
      }
    });

    const videos = Object.values(byVideo);
    let incidentsCount = 0;
    let vlmVerifiedCount = 0;
    let allClearCount = 0;

    videos.forEach(v => {
      v.verdict = verdicts.find(vd => (vd.video_path?.split(/[\\/]/).pop() || '') === v.name);
      v.topSusp = Object.entries(v.suspActions).sort((a, b) => b[1] - a[1]).slice(0, 4);

      const hs = v.verdict?.human_summary || v.verdict?.ai_summary_parsed?.human_summary;
      const el = v.verdict?.engineering_log || v.verdict?.ai_summary_parsed?.engineering_log;
      const rawFinal = v.verdict?.final_incident || v.verdict?.ai_summary_parsed?.final_incident;

      let incidentType = hs?.final_incident || rawFinal || 'CLEAR';
      let incidentTitle = hs?.title || v.verdict?.incident_title || v.verdict?.ai_summary_parsed?.incident_title;
      let incidentIcon = hs?.incident_icon || v.verdict?.incident_icon || v.verdict?.ai_summary_parsed?.incident_icon || '✅';
      let isVerified = Boolean(hs?.vlm_verified ?? v.verdict?.vlm_verified ?? v.verdict?.ai_summary_parsed?.vlm_verified);
      let vlmConfidence = hs?.vlm_confidence ?? v.verdict?.vlm_confidence ?? v.verdict?.ai_summary_parsed?.vlm_confidence;

      if (!incidentTitle) {
        if (incidentType === 'ANIMAL_ASSAULT' || v.topSusp.some(([a]) => a.includes('ANIMAL_ASSAULT') || a.includes('DOG_ATTACK'))) {
          incidentType = 'ANIMAL_ASSAULT';
          incidentTitle = 'Animal Assault (Dog Attack)';
          incidentIcon = '🐕';
        } else if (incidentType === 'FIRE_SMOKE' || v.topSusp.some(([a]) => a.includes('FIRE') || a.includes('SMOKE'))) {
          incidentType = 'FIRE_SMOKE';
          incidentTitle = 'Fire & Smoke Hazard';
          incidentIcon = '🔥';
        } else if (incidentType === 'FIGHT_ASSAULT' || v.topSusp.some(([a]) => a.includes('FIGHT') || a.includes('ASSAULT'))) {
          incidentType = 'FIGHT_ASSAULT';
          incidentTitle = 'Physical Altercation / Fight';
          incidentIcon = '🥊';
        } else if (incidentType === 'WEAPON' || v.topSusp.some(([a]) => a.includes('WEAPON') || a.includes('GUN') || a.includes('KNIFE'))) {
          incidentType = 'WEAPON';
          incidentTitle = 'Weapon Detected';
          incidentIcon = '🗡️';
        } else if (incidentType === 'ROUTINE_ANIMAL' || v.topSusp.some(([a]) => a.includes('ANIMAL') || a.includes('DOG'))) {
          incidentType = 'ROUTINE_ANIMAL';
          incidentTitle = 'Peaceful Animal Observed';
          incidentIcon = '🐾';
        } else {
          incidentType = 'CLEAR';
          incidentTitle = 'Routine Operations / Clear';
          incidentIcon = '✅';
        }
      }

      v.incident = {
        type: incidentType,
        title: incidentTitle,
        icon: incidentIcon,
        verified: isVerified,
        confidence: vlmConfidence ? (vlmConfidence > 1 ? Math.round(vlmConfidence) : Math.round(vlmConfidence * 100)) : null,
        humanSummary: hs,
        engineeringLog: el,
        whatHappened: cleanSummaryText(hs?.what_happened || v.verdict?.ai_summary || buildVideoSummary(v), {
          final_incident: incidentType,
          risk_level: hs?.risk_level || v.verdict?.risk_level,
          recommendation: hs?.recommendation || v.verdict?.recommendation,
        }),
        timeOfIncident: hs?.time_of_incident || null,
        advisory: hs?.advisory || null,
        recommendation: hs?.recommendation || v.verdict?.recommendation || 'Normal operations.',
        risk: hs?.risk_level || v.verdict?.risk_level || (incidentType === 'CLEAR' ? '[CLEAR] No Concerns' : '[ALERT] Detected')
      };

      if (incidentType !== 'CLEAR' && incidentType !== 'ROUTINE_ANIMAL') {
        incidentsCount += 1;
      } else {
        allClearCount += 1;
      }

      if (isVerified) {
        vlmVerifiedCount += 1;
      }
    });

    videos.sort((a, b) => {
      const aScore = a.incident.type !== 'CLEAR' ? (a.incident.verified ? 3 : 2) : 1;
      const bScore = b.incident.type !== 'CLEAR' ? (b.incident.verified ? 3 : 2) : 1;
      return bScore - aScore;
    });

    return {
      totalVideos: videos.length,
      incidentsCount,
      vlmVerifiedCount,
      allClearCount,
      videos,
    };
  }, [logs, verdicts]);

  const riskBadge = (lvl) => {
    if (!lvl) return null;
    const cls = lvl.includes('CRITICAL') || lvl.includes('HIGH')
      ? 'bg-red-100 text-red-700 border-red-200'
      : lvl.includes('MEDIUM')
        ? 'bg-yellow-100 text-yellow-800 border-yellow-200'
        : lvl.includes('ROUTINE')
          ? 'bg-sky-100 text-sky-800 border-sky-200'
          : 'bg-emerald-100 text-emerald-800 border-emerald-200';
    return <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>{lvl}</span>;
  };

  const downloadLogs = () => {
    const lines = [];
    lines.push('VIGILINX INCIDENT AUDIT REPORT');
    lines.push(`Generated: ${new Date().toLocaleString()}`);
    lines.push('');
    lines.push('INCIDENT SUMMARY');
    lines.push('================');
    lines.push(`Total videos analyzed: ${summary.totalVideos}`);
    lines.push(`Incidents detected: ${summary.incidentsCount}`);
    lines.push(`Verified by AI: ${summary.vlmVerifiedCount}`);
    lines.push(`All clear: ${summary.allClearCount}`);
    lines.push('');
    lines.push('RECORDED INCIDENTS');
    lines.push('==================');
    summary.videos.forEach((v, i) => {
      lines.push(`[${i + 1}] ${v.name} -> ${v.incident.title} (${v.incident.risk})`);
      lines.push(`    Verified by VLM: ${v.incident.verified ? `YES (${v.incident.confidence}%)` : 'NO (Fast-Path)'}`);
      lines.push(`    Summary: ${v.incident.whatHappened}`);
      if (v.incident.advisory) lines.push(`    Advisory: ${v.incident.advisory}`);
      lines.push('');
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vigilinx-incident-report-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={FileText}
        title="Incident Intelligence Center"
        subtitle="Final verified incident reports from the continuous multi-threat surveillance pipeline."
        accent={ACCENTS.red}
        actions={
          <>
            <button
              onClick={fetchData}
              className="px-4 py-2 bg-white text-gray-700 rounded-lg border border-gray-200 hover:border-rose-300 hover:text-rose-600 flex items-center gap-2 shadow-sm transition-colors"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button
              onClick={downloadLogs}
              disabled={summary.totalVideos === 0}
              className="px-4 py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700 flex items-center gap-2 disabled:bg-gray-300 disabled:cursor-not-allowed shadow-sm"
            >
              <Download size={16} />
              Export Incident Report
            </button>
          </>
        }
      />

      {/* Top Stat Cards: Executive Outcome View */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="rounded-xl border border-indigo-200 bg-indigo-50/70 p-4 shadow-sm hover:shadow-md transition-shadow">
          <p className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">Videos Analyzed</p>
          <p className="text-3xl font-bold text-indigo-900 mt-1">{summary.totalVideos}</p>
        </div>
        <div className="rounded-xl border border-rose-200 bg-rose-50/70 p-4 shadow-sm hover:shadow-md transition-shadow">
          <p className="text-xs font-semibold text-rose-700 uppercase tracking-wide">Incidents Detected</p>
          <p className="text-3xl font-bold text-rose-900 mt-1">{summary.incidentsCount}</p>
        </div>
        <div className="rounded-xl border border-violet-200 bg-violet-50/70 p-4 shadow-sm hover:shadow-md transition-shadow">
          <p className="text-xs font-semibold text-violet-700 uppercase tracking-wide flex items-center gap-1.5">
            <span>VLM Verified</span>
            <span className="text-[10px] bg-violet-200 text-violet-800 px-1.5 py-0.2 rounded font-bold">AI</span>
          </p>
          <p className="text-3xl font-bold text-violet-900 mt-1">{summary.vlmVerifiedCount}</p>
        </div>
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-4 shadow-sm hover:shadow-md transition-shadow">
          <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">All Clear</p>
          <p className="text-3xl font-bold text-emerald-900 mt-1">{summary.allClearCount}</p>
        </div>
      </div>

      {/* Main Incident Cards List */}
      <div className="space-y-5">
        {loading ? (
          <div className="p-8 text-center text-gray-500 flex items-center justify-center gap-2">
            <RefreshCw size={18} className="animate-spin text-rose-500" />
            <span>Loading surveillance incident records...</span>
          </div>
        ) : summary.videos.length === 0 ? (
          <div className="bg-white p-12 rounded-xl border-2 border-dashed border-gray-300 text-center">
            <FileText className="mx-auto mb-3 text-gray-300" size={44} />
            <p className="text-gray-700 font-semibold text-base">No surveillance footage analyzed yet</p>
            <p className="text-sm text-gray-400 mt-1">Once recordings are scanned, direct incident cards will appear here.</p>
          </div>
        ) : (
          summary.videos.map(v => {
            const inc = v.incident;
            const isIncident = inc.type !== 'CLEAR' && inc.type !== 'ROUTINE_ANIMAL';
            const isExpanded = expandedSummary[v.name] ?? isIncident;
            const isEngExpanded = expandedEngLogs[v.name];

            return (
              <div
                key={v.name}
                className={`bg-white rounded-xl border transition-all ${
                  isIncident
                    ? 'border-rose-200/80 shadow-sm hover:shadow-md ring-1 ring-rose-100'
                    : 'border-gray-200 shadow-xs hover:shadow-sm'
                }`}
              >
                {/* Header: Focused Incident Title & VLM Badge */}
                <div className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-100">
                  <div className="flex items-start sm:items-center gap-3.5 min-w-0">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl shadow-xs flex-shrink-0 ${
                      inc.type === 'ANIMAL_ASSAULT' ? 'bg-amber-100 border border-amber-300' :
                      inc.type === 'FIRE_SMOKE' ? 'bg-rose-100 border border-rose-300' :
                      inc.type === 'SMOKE_WARNING' ? 'bg-orange-100 border border-orange-300' :
                      inc.type === 'FIGHT_ASSAULT' ? 'bg-purple-100 border border-purple-300' :
                      inc.type === 'WEAPON' ? 'bg-red-100 border border-red-300' :
                      'bg-emerald-100 border border-emerald-300'
                    }`}>
                      {inc.icon}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-bold text-gray-900 text-lg leading-snug">{inc.title}</h3>
                        {inc.verified ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
                            <CheckCircle2 size={13} className="text-emerald-600" />
                            Verified by AI {inc.confidence ? `· ${inc.confidence}%` : ''}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                            ⚡ Neural Signal
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-1 font-mono flex items-center gap-2">
                        <span>📹 {v.name}</span>
                        {inc.timeOfIncident && (
                          <span className="font-semibold text-rose-700 bg-rose-50 px-1.5 py-0.2 rounded border border-rose-200">
                            Incident at {inc.timeOfIncident}
                          </span>
                        )}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5 self-end sm:self-center flex-shrink-0">
                    {riskBadge(inc.risk)}
                    <button
                      onClick={() => setExpandedSummary(prev => ({ ...prev, [v.name]: !isExpanded }))}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 border border-gray-300 transition-colors flex items-center gap-1.5"
                      title="Toggle Details"
                    >
                      <span>{isExpanded ? 'Hide' : 'Details'}</span>
                      {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    </button>
                  </div>
                </div>

                {/* Body Content */}
                {isExpanded && (
                  <div className="p-5 space-y-4 bg-gray-50/40">
                    {/* Layer 1: Clean Human Summary (Non-Technical Narrative) */}
                    <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-3">
                      <div className="flex items-center justify-between border-b border-gray-100 pb-2">
                        <div className="flex items-center gap-2 text-xs font-bold text-gray-700 uppercase tracking-wide">
                          <FileText size={15} className="text-rose-500" />
                          <span>Incident Overview</span>
                        </div>
                        {inc.verified && (
                          <span className="text-xs font-semibold text-violet-700 bg-violet-50 border border-violet-200 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <Sparkles size={12} className="text-violet-600" />
                            Grounded in Real Sensors
                          </span>
                        )}
                      </div>

                      <p className="text-sm leading-relaxed text-gray-800 font-medium">
                        {inc.whatHappened}
                      </p>

                      {inc.recommendation && (
                        <div className="text-xs p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-700">
                          <span className="font-bold text-slate-900">Standard Operating Protocol: </span>
                          <span>{inc.recommendation}</span>
                        </div>
                      )}

                      {inc.advisory && (
                        <div className="text-xs p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-1.5">
                          <span>💡</span>
                          <span><strong>Early Lead Advisory:</strong> {inc.advisory}</span>
                        </div>
                      )}

                      {v.verdict?.id && !inc.verified && (
                        <div className="pt-1">
                          <button
                            onClick={() => handleRunSummarize(v.verdict.id)}
                            disabled={summarizingId === v.verdict.id}
                            className="px-3.5 py-1.5 text-xs font-semibold text-violet-700 bg-violet-50 hover:bg-violet-100 border border-violet-200 rounded-lg shadow-2xs flex items-center gap-2 transition-all disabled:opacity-50"
                          >
                            <Sparkles size={14} className={summarizingId === v.verdict.id ? 'animate-spin text-violet-600' : 'text-violet-600'} />
                            {summarizingId === v.verdict.id ? 'Running Forensic Audit...' : 'Re-verify with AI'}
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Layer 2: Expandable Engineering Log (Model Breakdown & Frame Timeline) */}
                    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-2xs">
                      <button
                        onClick={() => setExpandedEngLogs(prev => ({ ...prev, [v.name]: !isEngExpanded }))}
                        className="w-full px-4 py-3 bg-gray-50/80 hover:bg-gray-100/80 text-left flex items-center justify-between text-xs font-bold text-gray-700 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <Terminal size={14} className="text-slate-600" />
                          <span>Engineering Log & Sensor Audit Trail</span>
                          <span className="font-normal text-gray-400">
                            ({inc.engineeringLog?.detection_timeline?.length || 0} telemetry events)
                          </span>
                        </div>
                        <div className="flex items-center gap-1 text-gray-500">
                          <span>{isEngExpanded ? 'Collapse' : 'Expand'}</span>
                          {isEngExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </div>
                      </button>

                      {isEngExpanded && (
                        <div className="p-4 space-y-3 bg-slate-900 text-slate-200 font-mono text-xs">
                          {/* Model Detection Breakdown */}
                          {inc.engineeringLog?.model_detections && (
                            <div className="p-3 bg-slate-800/80 rounded-lg border border-slate-700 text-[11px] space-y-1">
                              <p className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">Neural Model Attribution:</p>
                              <div className="flex flex-wrap gap-2 pt-1 text-slate-300">
                                <span className="bg-slate-700/80 px-2 py-0.5 rounded">
                                  COCO Animals: {inc.engineeringLog.model_detections.yolov8n_coco?.animals ?? 0}
                                </span>
                                <span className="bg-slate-700/80 px-2 py-0.5 rounded">
                                  Weapons: {inc.engineeringLog.model_detections.weapon_detector?.weapons ?? 0}
                                </span>
                                <span className="bg-slate-700/80 px-2 py-0.5 rounded">
                                  Fire/Smoke: {inc.engineeringLog.model_detections.fire_detector?.fires ?? 0}
                                </span>
                                <span className="bg-slate-700/80 px-2 py-0.5 rounded">
                                  Animal Assaults: {inc.engineeringLog.model_detections.animal_assault_engine?.assaults ?? 0}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Chronological Event Timeline */}
                          <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
                            {inc.engineeringLog?.detection_timeline?.length > 0 ? (
                              inc.engineeringLog.detection_timeline.map((evt, idx) => (
                                <div key={idx} className="flex items-start gap-2 py-1 border-b border-slate-800 text-[11px]">
                                  <span className="text-amber-400 font-bold w-14 flex-shrink-0">
                                    {typeof evt.timestamp_sec === 'number'
                                      ? `${Math.floor(evt.timestamp_sec / 60).toString().padStart(2, '0')}:${Math.floor(evt.timestamp_sec % 60).toString().padStart(2, '0')}`
                                      : '00:00'}
                                  </span>
                                  <span className={`px-1.5 py-0.2 rounded font-bold text-[10px] flex-shrink-0 ${
                                    evt.event === 'SENSOR_LEAD' ? 'bg-sky-950 text-sky-300 border border-sky-800' :
                                    evt.event === 'VLM_VERIFICATION' ? 'bg-violet-950 text-violet-300 border border-violet-800' :
                                    'bg-rose-950 text-rose-300 border border-rose-800'
                                  }`}>
                                    {evt.event}
                                  </span>
                                  <span className="text-slate-300">
                                    {evt.detail || evt.action || `${evt.threat_type}: ${evt.status}`}
                                    {evt.confidence ? ` (conf: ${typeof evt.confidence === 'number' ? evt.confidence.toFixed(2) : evt.confidence})` : ''}
                                    {evt.reasoning ? ` - "${evt.reasoning}"` : ''}
                                  </span>
                                </div>
                              ))
                            ) : (
                              <div className="text-slate-500 italic py-2">
                                No granular telemetry records logged for this session.
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

// Prompts Management View
const PromptsManagement = () => {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showGuide, setShowGuide] = useState(true);
  const [newPrompt, setNewPrompt] = useState({
    prompt_text: '',
    category: 'normal',
    is_suspicious: false,
  });

  useEffect(() => {
    fetchPrompts();
  }, []);

  const fetchPrompts = async () => {
    setLoading(true);
    try {
      const response = await authFetch(`${API_BASE}/api/prompts`);
      const data = await response.json();
      setPrompts(data);
    } catch (error) {
      console.error('Error fetching prompts:', error);
    } finally {
      setLoading(false);
    }
  };

  const deletePrompt = async (id) => {
    if (!window.confirm('Are you sure you want to delete this prompt?')) return;

    try {
      const response = await authFetch(`${API_BASE}/api/prompts/${id}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        fetchPrompts();
      } else {
        alert('Failed to delete prompt');
      }
    } catch (error) {
      alert('Error deleting prompt: ' + error.message);
    }
  };

  const addPrompt = async () => {
    if (!newPrompt.prompt_text.trim()) return;

    try {
      const response = await authFetch(`${API_BASE}/api/prompts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newPrompt),
      });

      if (response.ok) {
        setNewPrompt({ prompt_text: '', category: 'normal', is_suspicious: false });
        fetchPrompts();
      }
    } catch (error) {
      alert('Error adding prompt: ' + error.message);
    }
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={Shield}
        title="Detection Prompts"
        subtitle="Customize what the detector looks for in each video"
        accent={ACCENTS.purple}
        actions={
          <button
            onClick={fetchPrompts}
            className="px-4 py-2 bg-white text-gray-700 rounded-lg border border-gray-200 hover:border-fuchsia-300 hover:text-fuchsia-600 flex items-center gap-2 shadow-sm transition-colors"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        }
      />

      <div className="mb-6 rounded-xl border border-fuchsia-200 bg-gradient-to-br from-fuchsia-50/80 to-purple-50/40 overflow-hidden">
        <button
          onClick={() => setShowGuide(v => !v)}
          className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-fuchsia-100/40 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-fuchsia-100 text-fuchsia-600 flex items-center justify-center flex-shrink-0">
              <Shield size={18} />
            </div>
            <div>
              <h3 className="font-semibold text-gray-800">How to write good prompts</h3>
              <p className="text-xs text-gray-500">A quick guide to getting accurate detections</p>
            </div>
          </div>
          {showGuide ? <ChevronUp size={18} className="text-gray-400 flex-shrink-0" /> : <ChevronDown size={18} className="text-gray-400 flex-shrink-0" />}
        </button>

        {showGuide && (
          <div className="px-5 pb-5 grid md:grid-cols-2 gap-x-8 gap-y-2.5">
            {[
              { icon: Check, text: 'Keep prompts short and concrete — describe one clear scene, e.g. "a person breaking into a store".' },
              { icon: Eye, text: 'Describe what the camera would actually see: objects, actions and people, not intent or emotions.' },
              { icon: FileText, text: 'Aim for 4–8 words. The model scores every prompt independently, so clarity beats length.' },
              { icon: Shield, text: 'Add a few "Normal" prompts (e.g. "an empty room") as a baseline — this reduces false alarms.' },
              { icon: BarChart3, text: 'Avoid overlapping prompts that describe the same thing — distinct phrases score more cleanly.' },
              { icon: Bell, text: 'Mark the behaviours you want alerts for as "Suspicious". Normal prompts never alert.' },
            ].map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-start gap-2.5">
                <div className="w-6 h-6 rounded-md bg-white text-fuchsia-600 border border-fuchsia-200 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Icon size={13} />
                </div>
                <p className="text-sm text-gray-600 leading-relaxed">{text}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-6 mb-6">
        <div className="col-span-2 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h3 className="text-xl font-semibold mb-4">Existing Prompts</h3>

          <div className="space-y-2">
            {loading ? (
              <p className="text-gray-500">Loading...</p>
            ) : (
              prompts.map(prompt => (
                <div
                  key={prompt.id}
                  className={`p-3 rounded-lg border group relative ${prompt.is_suspicious
                    ? 'bg-red-50 border-red-200'
                    : 'bg-green-50 border-green-200'
                    }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="font-medium pr-8">{prompt.prompt_text}</span>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-1 rounded text-xs ${prompt.is_suspicious
                        ? 'bg-red-200 text-red-800'
                        : 'bg-green-200 text-green-800'
                        }`}>
                        {prompt.category}
                      </span>
                      <button
                        onClick={() => deletePrompt(prompt.id)}
                        className="p-1.5 text-red-500 hover:bg-red-100 rounded-md transition-colors opacity-0 group-hover:opacity-100"
                        title="Delete Prompt"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h3 className="text-xl font-semibold mb-4">Add New Prompt</h3>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Prompt Text
              </label>
              <textarea
                value={newPrompt.prompt_text}
                onChange={(e) => setNewPrompt({ ...newPrompt, prompt_text: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                rows="3"
                placeholder="e.g., a person looking around nervously"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Category
              </label>
              <select
                value={newPrompt.category}
                onChange={(e) => setNewPrompt({
                  ...newPrompt,
                  category: e.target.value,
                  is_suspicious: e.target.value === 'suspicious'
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="normal">Normal</option>
                <option value="suspicious">Suspicious</option>
              </select>
            </div>

            <button
              onClick={addPrompt}
              className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700"
            >
              Add Prompt
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// Verdicts View
const Verdicts = () => {
  const [verdicts, setVerdicts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [summarizingId, setSummarizingId] = useState(null);

  useEffect(() => {
    fetchVerdicts();
  }, []);

  const fetchVerdicts = async () => {
    setLoading(true);
    try {
      const response = await authFetch(`${API_BASE}/api/verdicts`);
      const data = await response.json();
      setVerdicts(data.verdicts || []);
    } catch (error) {
      console.error('Error fetching verdicts:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSummarize = async (verdictId) => {
    setSummarizingId(verdictId);
    try {
      const res = await authFetch(`${API_BASE}/api/video/summarize/${verdictId}`, {
        method: 'POST',
      });
      if (res.ok) {
        const sumData = await res.json();
        setVerdicts(prev =>
          prev.map(v =>
            v.id === verdictId
              ? { ...v, ai_summary: sumData.narrative_summary || JSON.stringify(sumData) }
              : v
          )
        );
      }
    } catch (err) {
      console.error('Failed to summarize:', err);
    } finally {
      setSummarizingId(null);
    }
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={BarChart3}
        title="Video Verdicts"
        subtitle="Full history of completed analyses & forensic VLM narratives"
        accent={ACCENTS.teal}
      />

      <div className="grid gap-4">
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : verdicts.length === 0 ? (
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 text-center text-gray-500">
            No verdicts found
          </div>
        ) : (
          verdicts.map(verdict => (
            <div key={verdict.id} className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="font-semibold text-lg">{verdict.video_path?.split(/[\\/]/).pop()}</h3>
                  <p className="text-sm text-gray-500">{new Date(verdict.timestamp).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  {(verdict.risk_level?.includes('CRITICAL') || verdict.risk_level?.includes('HIGH')) && (
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-50 text-red-700 border border-red-200">
                      🚩 FLAGGED
                    </span>
                  )}
                  {verdict.risk_level?.includes('Animal') && (
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-200">
                      🐕 Animal Assault
                    </span>
                  )}
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${verdict.risk_level?.includes('LOW') || verdict.risk_level?.includes('CLEAR') ? 'bg-green-100 text-green-800' :
                    verdict.risk_level?.includes('MEDIUM') ? 'bg-yellow-100 text-yellow-800' :
                      'bg-red-100 text-red-800'
                    }`}>
                    {verdict.risk_level}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-3">
                <div>
                  <p className="text-xs text-gray-500">Total Frames</p>
                  <p className="text-xl font-bold">{verdict.total_analyzed}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Suspicious</p>
                  <p className="text-xl font-bold text-red-600">{verdict.suspicious_frames}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Normal</p>
                  <p className="text-xl font-bold text-green-600">{verdict.normal_frames}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Footage Duration</p>
                  <p className="text-xl font-bold text-gray-700">{verdict.suspicious_percentage?.toFixed(1)}%</p>
                </div>
                <div className="bg-violet-50/60 p-2 rounded-lg border border-violet-100">
                  <p className="text-xs text-violet-700 font-semibold">AI Confidence</p>
                  <p className="text-xl font-bold text-violet-700">
                    {verdict.vlm_verified && verdict.vlm_confidence ? `${Math.round(verdict.vlm_confidence > 1 ? verdict.vlm_confidence : verdict.vlm_confidence * 100)}%` : 'Not checked'}
                  </p>
                </div>
              </div>

              <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded-lg border border-gray-100">{verdict.recommendation}</p>

              {(() => {
                const cleanSum = cleanSummaryText(verdict.human_summary?.what_happened || verdict.ai_summary, {
                  final_incident: verdict.final_incident,
                  risk_level: verdict.risk_level,
                  recommendation: verdict.recommendation,
                });
                return cleanSum ? (
                  <div className="mt-3 p-4 bg-gradient-to-r from-violet-50/80 via-purple-50/50 to-indigo-50/60 border border-violet-200/80 rounded-xl">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2 text-xs font-bold text-violet-800 uppercase tracking-wide">
                        <Sparkles size={14} className="text-violet-600" />
                        <span>AI Summary</span>
                      </div>
                      <span className="px-2 py-0.5 bg-violet-100 text-violet-700 rounded-full text-xs font-semibold">AI Native (Offline)</span>
                    </div>
                    <p className="text-sm text-gray-800 leading-relaxed font-medium">{cleanSum}</p>
                  </div>
                ) : (
                  <div className="mt-3 flex items-center justify-between p-3 bg-gray-50 rounded-xl border border-gray-200">
                    <span className="text-xs text-gray-500">No VLM forensic summary generated yet for this recording.</span>
                    <button
                      onClick={() => handleSummarize(verdict.id)}
                      disabled={summarizingId === verdict.id}
                      className="px-3 py-1.5 text-xs font-semibold text-violet-700 bg-white hover:bg-violet-50 border border-violet-200 rounded-lg shadow-sm flex items-center gap-1.5 transition-all disabled:opacity-50"
                    >
                      <Sparkles size={13} className={summarizingId === verdict.id ? 'animate-spin text-violet-600' : 'text-violet-600'} />
                      {summarizingId === verdict.id ? 'Analyzing with AI...' : 'Generate AI Summary'}
                    </button>
                  </div>
                );
              })()}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// System Settings View
const SystemSettings = () => {
  const [settings, setSettings] = useState({
    watch_dir: '',
    vlm_model: 'kimi-vl',
    alert_threshold_minutes: 60
  });
  const [alertSettings, setAlertSettings] = useState({
    alert_recipients: '',
    video_alert_template: '',
    inactivity_alert_template: ''
  });
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState('');

  useEffect(() => {
    fetchSettings();
    fetchAlertSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const response = await authFetch(`${API_BASE}/api/system-status`);
      const data = await response.json();
      if (data.settings) {
        setSettings(data.settings);
      }
    } catch (error) {
      console.error('Error fetching settings:', error);
    }
  };

  const fetchAlertSettings = async () => {
    try {
      const response = await authFetch(`${API_BASE}/api/settings/alerts`);
      const data = await response.json();
      setAlertSettings(data);
    } catch (error) {
      console.error('Error fetching alert settings:', error);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setSaveStatus('Saving...');
    try {
      // Save general settings
      const res1 = await authFetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });

      const res2 = await authFetch(`${API_BASE}/api/settings/alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(alertSettings),
      });

      if (res1.ok && res2.ok) {
        const data1 = await res1.json().catch(() => ({}));
        if (data1.settings?.watch_dir) {
          setSettings({ ...settings, watch_dir: data1.settings.watch_dir });
          setSaveStatus(`Settings saved. Monitoring active on: ${data1.settings.watch_dir}`);
        } else {
          setSaveStatus('Settings saved successfully!');
        }
        setTimeout(() => setSaveStatus(''), 4000);
      } else {
        setSaveStatus('Failed to save some settings');
      }
    } catch (error) {
      setSaveStatus('Error saving settings: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={Settings}
        title="System Settings"
        subtitle="Configure monitoring, directories and alerts"
        accent={ACCENTS.slate}
      />

      <div className="space-y-6 max-w-4xl">
        <SettingsCard icon={Settings} title="General Settings" subtitle="Where Vigilinx watches and how it analyzes">
          <div className="space-y-5">
            <Field label="Watchdog Directory" hint="Path monitored for new videos. ~ and relative paths work.">
              <input
                type="text"
                value={settings.watch_dir}
                onChange={(e) => setSettings({ ...settings, watch_dir: e.target.value })}
                placeholder="e.g., /Users/you/Desktop/videos"
                className={INPUT_CLS}
              />
            </Field>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="VLM Model">
                <select
                  value={settings.vlm_model}
                  onChange={(e) => setSettings({ ...settings, vlm_model: e.target.value })}
                  className={INPUT_CLS}
                >
                  <option value="kimi-vl">Kimi-VL A3B (Local, Recommended)</option>
                  <option value="xclip">X-CLIP (Lightweight Fallback)</option>
                </select>
              </Field>
              <Field label="Inactivity Threshold (Min)" hint="Alert if no new video for this long.">
                <input
                  type="number"
                  value={settings.alert_threshold_minutes}
                  onChange={(e) => setSettings({ ...settings, alert_threshold_minutes: parseInt(e.target.value) })}
                  className={INPUT_CLS}
                />
              </Field>
            </div>
          </div>
        </SettingsCard>

        <SettingsCard icon={Bell} title="Alert & Email Configuration" subtitle="Who gets notified and what the alert looks like">
          <div className="space-y-5">
            <Field label="Alert Recipients" hint="Press Enter or comma to add each recipient. Click the × to remove.">
              <ChipInput
                value={alertSettings.alert_recipients}
                onChange={(v) => setAlertSettings({ ...alertSettings, alert_recipients: v })}
                placeholder="type an email, e.g. admin@example.com"
              />
            </Field>

            <Field label="Video Alert Message Template" hint="Placeholders: {video_name}, {risk_level}, {recommendation}, {stats}">
              <textarea
                value={alertSettings.video_alert_template}
                onChange={(e) => setAlertSettings({ ...alertSettings, video_alert_template: e.target.value })}
                className={`${TEXTAREA_CLS} h-32`}
                placeholder="Placeholders: {video_name}, {risk_level}, {recommendation}, {stats}"
              />
            </Field>

            <Field label="Inactivity Alert Message Template" hint="Placeholders: {watch_path}, {minutes}">
              <textarea
                value={alertSettings.inactivity_alert_template}
                onChange={(e) => setAlertSettings({ ...alertSettings, inactivity_alert_template: e.target.value })}
                className={`${TEXTAREA_CLS} h-24`}
                placeholder="Placeholders: {watch_path}, {minutes}"
              />
            </Field>
          </div>

          <div className="mt-6 pt-5 border-t border-gray-100 flex flex-wrap items-center gap-3">
            <button
              onClick={async () => {
                const recipient = alertSettings.alert_recipients?.split(',')[0]?.trim();
                if (!recipient) {
                  setSaveStatus('No alert recipients configured. Add one above first.');
                  setTimeout(() => setSaveStatus(''), 3000);
                  return;
                }
                setSaveStatus('Sending test email...');
                try {
                  const res = await authFetch(`${API_BASE}/api/email/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ recipient }),
                  });
                  const data = await res.json();
                  if (res.ok) {
                    setSaveStatus('Test email sent successfully! Check your inbox.');
                  } else {
                    setSaveStatus('Test email failed: ' + (data.detail || 'Unknown error'));
                  }
                } catch (err) {
                  setSaveStatus('Test email error: ' + err.message);
                }
                setTimeout(() => setSaveStatus(''), 5000);
              }}
              className="bg-green-600 text-white px-5 py-2.5 rounded-xl font-bold hover:bg-green-700 transition-colors shadow-sm flex items-center gap-2"
            >
              <Send size={16} /> Send Test Email
            </button>
            <span className="text-xs text-gray-500">Sends to the first recipient in the list above</span>
          </div>
        </SettingsCard>

        <div className="flex items-center justify-between p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <span className={`text-sm font-medium ${saveStatus.includes('success') ? 'text-green-600' : saveStatus ? 'text-red-600' : 'text-gray-400'}`}>
            {saveStatus || 'Changes are applied when you save.'}
          </span>
          <button
            onClick={handleSave}
            disabled={loading}
            className="bg-blue-600 text-white px-8 py-2.5 rounded-xl font-bold hover:bg-blue-700 disabled:bg-gray-400 transition-colors shadow-sm"
          >
            {loading ? 'Saving Changes...' : 'Save All Settings'}
          </button>
        </div>
      </div>
    </div>
  );
};

// CCTV Management View
const CCTVManagement = () => {
  const [ips, setIps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newIp, setNewIp] = useState('');
  const [newLocation, setNewLocation] = useState('');

  useEffect(() => {
    fetchIps();
    const interval = setInterval(fetchIps, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchIps = async () => {
    try {
      const response = await authFetch(`${API_BASE}/api/cctv`);
      const data = await response.json();
      setIps(data);
    } catch (error) {
      console.error('Error fetching CCTV IPs:', error);
    }
  };

  const addIp = async () => {
    if (!newIp || !newLocation) return;
    setLoading(true);
    try {
      const response = await authFetch(`${API_BASE}/api/cctv`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip_address: newIp, location: newLocation, user_id: 1 }),
      });
      if (response.ok) {
        setNewIp('');
        setNewLocation('');
        fetchIps();
      }
    } catch (error) {
      alert('Error adding CCTV: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteIp = async (id) => {
    if (!window.confirm('Are you sure you want to remove this CCTV?')) return;
    try {
      const response = await authFetch(`${API_BASE}/api/cctv/${id}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        fetchIps();
      }
    } catch (error) {
      alert('Error deleting CCTV: ' + error.message);
    }
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={Activity}
        title="CCTV Monitoring"
        subtitle="Manage connected camera feeds"
        accent={ACCENTS.cyan}
        actions={
          <button
            onClick={fetchIps}
            className="px-4 py-2 bg-white text-gray-700 rounded-lg border border-gray-200 hover:border-cyan-300 hover:text-cyan-600 flex items-center gap-2 shadow-sm transition-colors"
          >
            <RefreshCw size={16} />
            Refresh Status
          </button>
        }
      />

      <div className="grid grid-cols-3 gap-6 mb-8">
        <div className="col-span-1 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h3 className="text-xl font-semibold mb-4">Add New Camera</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">IP Address</label>
              <input
                type="text"
                value={newIp}
                onChange={(e) => setNewIp(e.target.value)}
                placeholder="e.g., 192.168.1.10"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Location</label>
              <input
                type="text"
                value={newLocation}
                onChange={(e) => setNewLocation(e.target.value)}
                placeholder="e.g., Main Entrance"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <button
              onClick={addIp}
              disabled={loading || !newIp || !newLocation}
              className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400"
            >
              {loading ? 'Adding...' : 'Add Camera'}
            </button>
          </div>
        </div>

        <div className="col-span-2 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h3 className="text-xl font-semibold mb-4">Monitored Cameras</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Location</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">IP Address</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Last Checked</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {ips.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="px-4 py-4 text-center text-gray-500">No cameras added yet</td>
                  </tr>
                ) : (
                  ips.map(ip => (
                    <tr key={ip.id}>
                      <td className="px-4 py-3 text-sm font-medium">{ip.location}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{ip.ip_address}</td>
                      <td className="px-4 py-3 text-sm">
                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${ip.status === 'online' ? 'bg-green-100 text-green-800' :
                          ip.status === 'offline' ? 'bg-red-100 text-red-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                          {ip.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {new Date(ip.last_checked).toLocaleTimeString()}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <button onClick={() => deleteIp(ip.id)} className="text-red-600 hover:text-red-900">
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

// Admin Panel View
const AdminPanel = () => {
  const [users, setUsers] = useState([]);
  const [allPermissions, setAllPermissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingPerms, setEditingPerms] = useState(null);
  const [permsDraft, setPermsDraft] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [changingPassword, setChangingPassword] = useState(null);
  const [newPassword, setNewPassword] = useState('');
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', email: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const clearMessages = () => { setError(''); setSuccess(''); };
  const showSuccess = (msg) => { setSuccess(msg); setTimeout(() => setSuccess(''), 3000); };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [usersRes, permsRes] = await Promise.all([
        authFetch(`${API_BASE}/api/admin/users`),
        authFetch(`${API_BASE}/api/admin/permissions`),
      ]);
      setUsers(await usersRes.json());
      setAllPermissions(await permsRes.json());
    } catch (err) {
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreateUser = async () => {
    clearMessages();
    if (!newUser.username.trim() || !newUser.password.trim()) {
      setError('Username and password are required');
      return;
    }
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUser),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Failed to create user');
      }
      setNewUser({ username: '', password: '', display_name: '', email: '' });
      setShowCreateForm(false);
      showSuccess('User created successfully');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteUser = async (userId, username) => {
    if (!window.confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    clearMessages();
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users/${userId}`, { method: 'DELETE' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Failed to delete user');
      }
      showSuccess('User deleted');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleToggleActive = async (userId, currentlyActive) => {
    clearMessages();
    try {
      await authFetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !currentlyActive }),
      });
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSavePermissions = async (userId, permissions) => {
    clearMessages();
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users/${userId}/permissions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissions }),
      });
      if (!res.ok) throw new Error('Failed to save permissions');
      setEditingPerms(null);
      setPermsDraft(null);
      showSuccess('Permissions updated');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUpdateUser = async (userId) => {
    clearMessages();
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingUser),
      });
      if (!res.ok) throw new Error('Failed to update user');
      setEditingUser(null);
      showSuccess('User updated');
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleChangePassword = async (userId) => {
    clearMessages();
    if (!newPassword.trim()) { setError('Password cannot be empty'); return; }
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users/${userId}/password`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword }),
      });
      if (!res.ok) throw new Error('Failed to change password');
      setChangingPassword(null);
      setNewPassword('');
      showSuccess('Password changed');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="p-8">
      <PageHeader
        icon={Shield}
        title="Admin Panel"
        subtitle="Manage users and page permissions"
        accent={ACCENTS.amber}
        actions={
          <div className="flex gap-2">
            <button onClick={() => { setShowCreateForm(!showCreateForm); clearMessages(); }}
              className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 flex items-center gap-2 shadow-sm">
              <Plus size={16} /> New User
            </button>
            <button onClick={fetchData}
              className="px-4 py-2 bg-white text-gray-700 rounded-lg border border-gray-200 hover:border-amber-300 hover:text-amber-600 flex items-center gap-2 shadow-sm transition-colors">
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        }
      />

      {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex justify-between items-center">{error} <button onClick={() => setError('')}><X size={14} /></button></div>}
      {success && <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 flex items-center gap-2"><Check size={14} /> {success}</div>}

      {showCreateForm && (
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 mb-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><Plus size={18} /> Create New User</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username *</label>
              <input type="text" value={newUser.username} onChange={e => setNewUser({ ...newUser, username: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="johndoe" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password *</label>
              <input type="text" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="password" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
              <input type="text" value={newUser.display_name} onChange={e => setNewUser({ ...newUser, display_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="John Doe" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input type="email" value={newUser.email} onChange={e => setNewUser({ ...newUser, email: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="john@example.com" />
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={handleCreateUser} className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">Create User</button>
            <button onClick={() => setShowCreateForm(false)} className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300">Cancel</button>
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Pages</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Login</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr><td colSpan="5" className="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
              ) : users.map(u => (
                <tr key={u.id} className={`${!u.is_active ? 'bg-gray-50 opacity-60' : 'hover:bg-gray-50'}`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                        {(u.display_name || u.username)[0].toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{u.display_name || u.username}</p>
                        <p className="text-xs text-gray-500">@{u.username}{u.email ? ` · ${u.email}` : ''}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => handleToggleActive(u.id, u.is_active)}
                      className={`text-xs px-2 py-1 rounded font-medium ${u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {u.is_active ? 'Active' : 'Disabled'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(u.permissions || []).slice(0, 3).map(p => (
                        <span key={p} className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">{p}</span>
                      ))}
                      {(u.permissions || []).length > 3 && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">+{u.permissions.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button onClick={() => {
                          if (editingPerms === u.id) {
                            setEditingPerms(null);
                            setPermsDraft(null);
                          } else {
                            setEditingPerms(u.id);
                            setPermsDraft(new Set(u.permissions || []));
                          }
                          setEditingUser(null);
                          setChangingPassword(null);
                        }}
                        className="p-1.5 text-blue-600 hover:bg-blue-50 rounded" title="Edit Permissions">
                        <Shield size={14} />
                      </button>
                      <button onClick={() => { setEditingUser(editingUser?.id === u.id ? null : { id: u.id, display_name: u.display_name || '', email: u.email || '' }); setEditingPerms(null); setChangingPassword(null); }}
                        className="p-1.5 text-gray-600 hover:bg-gray-50 rounded" title="Edit User">
                        <Edit2 size={14} />
                      </button>
                      <button onClick={() => { setChangingPassword(changingPassword === u.id ? null : u.id); setNewPassword(''); setEditingPerms(null); setEditingUser(null); }}
                        className="p-1.5 text-yellow-600 hover:bg-yellow-50 rounded" title="Change Password">
                        <Key size={14} />
                      </button>
                      <button onClick={() => handleDeleteUser(u.id, u.username)}
                        className="p-1.5 text-red-500 hover:bg-red-50 rounded" title="Delete User">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editingPerms && (() => {
        const targetUser = users.find(u => u.id === editingPerms);
        if (!targetUser) return null;
        const originalPerms = new Set(targetUser.permissions || []);
        const draft = permsDraft || originalPerms;
        const togglePerm = (key) => {
          const next = new Set(draft);
          next.has(key) ? next.delete(key) : next.add(key);
          setPermsDraft(next);
        };
        const isDirty =
          draft.size !== originalPerms.size ||
          [...draft].some(k => !originalPerms.has(k));
        const closePopup = () => { setEditingPerms(null); setPermsDraft(null); };
        const savePopup = () => handleSavePermissions(editingPerms, [...draft]);
        return (
          <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-blue-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Shield size={18} className="text-blue-600" />
                Page Permissions for <span className="text-blue-600">@{targetUser.username}</span>
              </h3>
              <button onClick={closePopup} className="p-1 hover:bg-gray-100 rounded"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {allPermissions.map(perm => (
                <label key={perm.key}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    draft.has(perm.key) ? 'bg-blue-50 border-blue-300' : 'bg-gray-50 border-gray-200 hover:bg-gray-100'
                  }`}>
                  <input type="checkbox" checked={draft.has(perm.key)} onChange={() => togglePerm(perm.key)}
                    className="w-4 h-4 text-blue-600 rounded" />
                  <div>
                    <p className="text-sm font-medium text-gray-800">{perm.label}</p>
                    <p className="text-xs text-gray-500">{perm.description}</p>
                  </div>
                </label>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              {isDirty && <span className="text-xs text-amber-600 mr-2">Unsaved changes</span>}
              <button onClick={closePopup}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium">
                Cancel
              </button>
              <button onClick={savePopup} disabled={!isDirty}
                className={`px-6 py-2 rounded-lg text-sm font-medium flex items-center gap-2 ${
                  isDirty
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                }`}>
                <Check size={16} /> Save Changes
              </button>
            </div>
          </div>
        );
      })()}

      {editingUser && (
        <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2"><Edit2 size={18} /> Edit User</h3>
            <button onClick={() => setEditingUser(null)} className="p-1 hover:bg-gray-100 rounded"><X size={18} /></button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
              <input type="text" value={editingUser.display_name} onChange={e => setEditingUser({ ...editingUser, display_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input type="email" value={editingUser.email} onChange={e => setEditingUser({ ...editingUser, email: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
          </div>
          <button onClick={() => handleUpdateUser(editingUser.id)}
            className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">Save Changes</button>
        </div>
      )}

      {changingPassword && (
        <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-yellow-200">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Key size={18} className="text-yellow-600" />
              Change Password for <span className="text-yellow-600">@{users.find(u => u.id === changingPassword)?.username}</span>
            </h3>
            <button onClick={() => { setChangingPassword(null); setNewPassword(''); }} className="p-1 hover:bg-gray-100 rounded"><X size={18} /></button>
          </div>
          <div className="flex gap-3">
            <input type="text" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Enter new password"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg" />
            <button onClick={() => handleChangePassword(changingPassword)}
              className="px-6 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 font-medium">Set Password</button>
          </div>
        </div>
      )}
    </div>
  );
};

// Subscription Expired Paywall
const SubscriptionExpired = ({ subscription }) => {
  const trialEndDate = subscription?.trial_end
    ? new Date(subscription.trial_end).toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric',
      })
    : 'N/A';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-lg w-full">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-red-500/20 mb-4">
            <ShieldOff className="text-red-400" size={40} />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">Free Trial Expired</h1>
          <p className="text-blue-200/70">
            Your 30-day free trial of Vigilinx ended on {trialEndDate}.
          </p>
        </div>

        <div className="bg-white/10 backdrop-blur-lg rounded-2xl border border-white/20 p-8 shadow-2xl">
          <div className="text-center mb-4">
            <Lock className="mx-auto text-yellow-400 mb-3" size={32} />
            <h2 className="text-xl font-semibold text-white mb-2">Subscribe to Continue</h2>
            <p className="text-sm text-blue-200/60">
              Your free trial period has ended. Please purchase a subscription to continue using Vigilinx and access all features.
            </p>
          </div>

          <div className="mt-6 pt-6 border-t border-white/10 text-center">
            <p className="text-sm text-blue-200/60 mb-4">
              Contact the iTechSeed sales team to purchase a subscription
            </p>
          </div>
        </div>

        <p className="text-center text-xs text-blue-200/30 mt-6">
          Vigilinx &mdash; iTechSeed
        </p>
      </div>
    </div>
  );
};

// Trial Banner (shown when trial is active but nearing expiration)
const TrialBanner = ({ daysRemaining }) => {
  if (daysRemaining > 7) return null;
  const urgency = daysRemaining <= 3;
  return (
    <div className={`px-4 py-2 text-center text-sm font-medium ${
      urgency ? 'bg-red-600 text-white' : 'bg-yellow-500 text-yellow-900'
    }`}>
      {daysRemaining === 0
        ? 'Your free trial expires today! Purchase a license to avoid interruption.'
        : `Your free trial expires in ${daysRemaining} day${daysRemaining !== 1 ? 's' : ''}. Contact sales@itechseed.com to purchase a license.`}
    </div>
  );
};

// Main App
export default function App() {
  const [token, setToken] = useState(() => getStoredToken());
  const [user, setUser] = useState(() => getStoredUser());
  const [currentView, setCurrentView] = useState(() => {
    const stored = getStoredUser();
    return getDefaultView(stored?.permissions) || 'dashboard';
  });
  const [isWatchdogRunning, setIsWatchdogRunning] = useState(false);
  const [subscription, setSubscription] = useState(null);
  const [subLoading, setSubLoading] = useState(true);

  const handleLogin = (newToken, newUser) => {
    setToken(newToken);
    setUser(newUser);
    // Jump straight to a page the new user actually has permission for,
    // so the main panel doesn't render an empty/locked page right after login.
    const next = getDefaultView(newUser?.permissions);
    if (next) setCurrentView(next);
  };

  // If the currently selected page is no longer in the user's permissions
  // (e.g. admin revoked it while they were logged in), fall back to a permitted one.
  useEffect(() => {
    if (!user) return;
    const perms = user.permissions || [];
    if (currentView && !perms.includes(currentView)) {
      const fallback = getDefaultView(perms);
      if (fallback) setCurrentView(fallback);
    }
  }, [user, currentView]);

  const handleLogout = useCallback(() => {
    localStorage.removeItem('vigilinx_token');
    localStorage.removeItem('vigilinx_user');
    setToken(null);
    setUser(null);
    setSubscription(null);
  }, []);

  const fetchSubscription = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/subscription/status`);
      const data = await response.json();
      setSubscription(data);
    } catch (error) {
      console.error('Error fetching subscription:', error);
    } finally {
      setSubLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!token) {
      setSubLoading(false);
      return;
    }
    setSubLoading(true);
    fetchSubscription();
    const interval = setInterval(fetchSubscription, 60000);
    return () => clearInterval(interval);
  }, [fetchSubscription, token]);

  useEffect(() => {
    if (!token || subscription?.expired) return;

    const fetchSystemStatus = async () => {
      try {
        const response = await authFetch(`${API_BASE}/api/system-status`);
        if (response.status === 401) {
          handleLogout();
          return;
        }
        const data = await response.json();
        setIsWatchdogRunning(data.watchdog_running);
      } catch (error) {
        console.error('Error fetching system status:', error);
        setIsWatchdogRunning(false);
      }
    };

    fetchSystemStatus();
    const interval = setInterval(fetchSystemStatus, 5000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, subscription?.expired]);

  // No token → show login page immediately on first render
  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  if (subLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <RefreshCw className="text-blue-400 animate-spin" size={32} />
      </div>
    );
  }

  if (subscription?.expired) {
    return (
      <SubscriptionExpired subscription={subscription} />
    );
  }

  return (
    <AuthContext.Provider value={{ token, user, logout: handleLogout }}>
      <div className="flex flex-col h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-blue-50/60">
        {/* days_remaining is -1 on paid/unlimited plans: no banner then */}
        {subscription && subscription.plan !== 'paid' && subscription.days_remaining >= 0 && (
          <TrialBanner daysRemaining={subscription.days_remaining} />
        )}
        <div className="flex flex-1 min-h-0">
          <Sidebar
            currentView={currentView}
            setCurrentView={setCurrentView}
            isWatchdogRunning={isWatchdogRunning}
            user={user}
            onLogout={handleLogout}
          />

          <div className="flex-1 overflow-y-auto">
            {(() => {
              const perms = user?.permissions || [];
              if (perms.length === 0) {
                return (
                  <div className="flex flex-col items-center justify-center h-full p-8 text-center">
                    <ShieldOff className="text-gray-400 mb-4" size={48} />
                    <h2 className="text-xl font-semibold text-gray-700 mb-2">No Pages Available</h2>
                    <p className="text-sm text-gray-500 max-w-md">
                      Your account does not have permission to access any pages yet.
                      Please contact your administrator to grant access.
                    </p>
                    <button
                      onClick={handleLogout}
                      className="mt-6 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                    >
                      Sign Out
                    </button>
                  </div>
                );
              }
              if (!perms.includes(currentView)) {
                // Effect-driven fallback hasn't fired yet; render nothing for one tick.
                return null;
              }
              return (
                <>
                  {currentView === 'dashboard' && (
                    <Dashboard
                      isWatchdogRunning={isWatchdogRunning}
                      setCurrentView={setCurrentView}
                    />
                  )}
                  {currentView === 'analytics' && <Analytics setCurrentView={setCurrentView} />}
                  {currentView === 'analyze' && <VideoAnalysis />}
                  {currentView === 'detections' && <DetectionLogs />}
                  {currentView === 'prompts' && <PromptsManagement />}
                  {currentView === 'verdicts' && <Verdicts />}
                  {currentView === 'cctv' && <CCTVManagement />}
                  {currentView === 'settings' && <SystemSettings />}
                  {currentView === 'admin' && <AdminPanel />}
                </>
              );
            })()}
          </div>
        </div>
      </div>
    </AuthContext.Provider>
  );
}
