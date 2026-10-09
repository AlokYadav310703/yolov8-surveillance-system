const PAGES = [
  ["dashboard", "Dashboard"],
  ["live", "Live view"],
  ["people", "People"],
  ["logs", "Activity log"],
  ["settings", "Settings"],
];

export default function Sidebar({ page, onNavigate, cameras, detector }) {
  const online = cameras.filter((c) => c.online).length;
  const dot = online ? "on" : cameras.length ? "off" : "";
  return (
    <aside className="side">
      <div className="brand">
        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 9V6a2 2 0 0 1 2-2h3M15 4h3a2 2 0 0 1 2 2v3M20 15v3a2 2 0 0 1-2 2h-3M9 20H6a2 2 0 0 1-2-2v-3" />
          <circle cx="12" cy="11" r="3" />
          <path d="M7.5 17c.8-2 2.4-3 4.5-3s3.7 1 4.5 3" />
        </svg>
        <span>FaceWatch</span>
      </div>
      <nav>
        {PAGES.map(([id, label]) => (
          <button key={id} className={page === id ? "active" : ""} onClick={() => onNavigate(id)}>{label}</button>
        ))}
      </nav>
      <div className="side-foot">
        <div>
          <span className={"dot " + dot} />{" "}
          {cameras.length ? `${online} of ${cameras.length} camera${cameras.length > 1 ? "s" : ""} online` : "No cameras found"}
        </div>
        {detector && <div className="muted">{detector} + SFace</div>}
      </div>
    </aside>
  );
}
