import { useEffect, useState } from 'react';
import type { WorldSnapshot } from './types/domain-contracts';
import { createConfiguredSimulationRuntime } from './lib/simulation-runtime';

const navigation = [
  { id: 'overview', label: 'World overview', icon: '◈' },
  { id: 'people', label: 'People & NPCs', icon: '♙' },
  { id: 'districts', label: 'Districts', icon: '▦' },
  { id: 'society', label: 'Society', icon: '◎' },
  { id: 'economy', label: 'Economy', icon: '◇' },
  { id: 'history', label: 'World history', icon: '◷' },
  { id: 'campaigns', label: 'Campaigns', icon: '⌂' },
];

const activity = [
  { icon: '↗', title: 'Autonomous runtime is not connected', detail: 'The UI is ready for the simulation adapter; no live world state is being fabricated.', time: 'SYSTEM' },
  { icon: '♧', title: 'NPC population systems', detail: 'Psychology, goals, memory and social systems exist in the Python reference layer.', time: 'ENGINE' },
  { icon: '▤', title: 'Persistent campaign history', detail: 'World checkpoints and archived-life continuity are implemented in the reference engine.', time: 'ENGINE' },
  { icon: '⌘', title: 'C++ runtime integration', detail: 'Portable C++ core exists; Unreal presentation and runtime adapter remain future work.', time: 'ENGINE' },
];

const pageDescriptions: Record<string, string> = {
  people: 'Inspect individual lives, memories, goals, relationships and current activities. Live NPC queries become available when the world-runtime API is connected.',
  districts: 'Explore district conditions, infrastructure, neighborhood development and local population dynamics.',
  society: 'Explore relationships, social networks, institutions, law, politics and the flow of information through the population.',
  economy: 'View household finances, employment, businesses, production, markets and district-level economic conditions.',
  history: 'Follow world events, historical consequences, campaign timelines and archived lives.',
  campaigns: 'Create and resume campaigns, inspect archived timelines and manage persistent player-world state.',
};

export function App() {
  const [activePage, setActivePage] = useState('overview');
  const [connection, setConnection] = useState<'unconfigured' | 'connecting' | 'connected' | 'disconnected'>('unconfigured');
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null);

  useEffect(() => {
    const runtime = createConfiguredSimulationRuntime();
    if (!runtime) return;
    let mounted = true;
    setConnection('connecting');
    void runtime.getWorldSnapshot().then((result) => {
      if (!mounted) return;
      if (result.ok) {
        setSnapshot(result.value);
        setConnection('connected');
      } else {
        setConnection('disconnected');
      }
    });
    const unsubscribe = runtime.subscribe((next) => {
      if (!mounted) return;
      setSnapshot(next);
      setConnection('connected');
    }, () => {
      if (mounted) setConnection('disconnected');
    });
    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);
  const active = navigation.find((item) => item.id === activePage) ?? navigation[0];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">L</div>
          <div><div className="brand-name">LIFE ITSELF</div><div className="brand-sub">SIMULATED REALITY</div></div>
        </div>
        <nav aria-label="Main navigation">
          <div className="nav-label">WORLD SYSTEMS</div>
          <div className="nav-list">
            {navigation.map((item) => (
              <button key={item.id} className={`nav-item ${activePage === item.id ? 'active' : ''}`} onClick={() => setActivePage(item.id)} aria-current={activePage === item.id ? 'page' : undefined}>
                <span className="nav-icon" aria-hidden="true">{item.icon}</span>{item.label}
              </button>
            ))}
          </div>
        </nav>
        <div className="sidebar-bottom">
          <strong>Simulation connection</strong>
          <p><span className="status-dot" />Reference engine only</p>
          <p>The live Unreal/runtime bridge has not been connected.</p>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div><div className="eyebrow">SIMULATED REALITY ENGINE</div><div className="topbar-title">Persistent world management</div></div>
          <div className="top-actions"><span className="pill">LOCAL APPLICATION PREVIEW</span><div className="avatar" aria-label="Guest profile">G</div></div>
        </header>

        {activePage === 'overview' ? (
          <>
            <section className="page-heading">
              <div><div className="eyebrow">WORLD CONTROL CENTER</div><h1>A world of its own.</h1><p className="subtitle">A systemic life simulation where people build lives, form relationships and shape a persistent world.</p></div>
              <div className="date-label">ENGINE STATUS · FOUNDATION</div>
            </section>
            <section className="stats-grid" aria-label="Engine capability summary">
              <article className="stat-card"><div className="stat-label">REFERENCE SYSTEMS</div><div className="stat-value">100+</div><div className="stat-foot">Python domain modules and adapters</div></article>
              <article className="stat-card"><div className="stat-label">CORE LANGUAGE</div><div className="stat-value">C++20</div><div className="stat-foot">Portable native simulation library</div></article>
              <article className="stat-card"><div className="stat-label">PERSISTENCE</div><div className="stat-value">Active</div><div className="stat-foot"><em>✓</em> Versioned checkpoints and replay</div></article>
              <article className="stat-card"><div className="stat-label">GAME PRESENTATION</div><div className="stat-value">Pending</div><div className="stat-foot">Unreal adapter not yet implemented</div></article>
            </section>
            <section className="content-grid">
              <article className="panel">
                <div className="panel-heading"><h2>World state</h2><span>CONNECTION OVERVIEW</span></div>
                <div className="world-preview"><div className="world-overlay"><strong><span className="status-dot" />Simulation adapter offline</strong><p>Connect the runtime to display live world telemetry.</p></div></div>
              </article>
              <article className="panel">
                <div className="panel-heading"><h2>Engine activity</h2><span>IMPLEMENTATION STATUS</span></div>
                <div className="activity-list">{activity.map((item) => <div className="activity" key={item.title}><div className="activity-icon">{item.icon}</div><div><strong>{item.title}</strong><small>{item.detail}</small></div><time>{item.time}</time></div>)}</div>
              </article>
            </section>
            <section className="feature-grid">
              <article className="feature-card"><div className="feature-icon">♧</div><h3>Individual lives</h3><p>Memory, personality, identity, goals and emotional development.</p></article>
              <article className="feature-card"><div className="feature-icon">◎</div><h3>Living society</h3><p>Relationships, trust, beliefs, institutions and social consequences.</p></article>
              <article className="feature-card"><div className="feature-icon">◷</div><h3>Persistent history</h3><p>Events, world checkpoints, archived timelines and campaign continuity.</p></article>
            </section>
          </>
        ) : (
          <>
            <section className="page-heading"><div><div className="eyebrow">WORLD SYSTEMS / {active.label.toUpperCase()}</div><h1>{active.label}</h1><p className="subtitle">Life Itself simulation management.</p></div></section>
            <section className="page-placeholder"><div className="eyebrow">DOMAIN INTERFACE</div><h2>{active.label} interface foundation</h2><p>{pageDescriptions[activePage] ?? 'This application section is being prepared for its domain integration.'}</p><p>It will consume versioned world snapshots and issue validated simulation commands through the application API. Until that adapter exists, this screen intentionally displays no invented simulation data.</p></section>
          </>
        )}
        <div className="footer-note">LIFE ITSELF · SIMULATED REALITY ENGINE · APPLICATION FOUNDATION</div>
      </main>
    </div>
  );
}
