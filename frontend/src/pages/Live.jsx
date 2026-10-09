import LiveCanvas from "../components/LiveCanvas";
import { useCameraToggle } from "../hooks";

export default function Live({ cameras, reload }) {
  const toggle = useCameraToggle(reload);
  return (
    <section>
      <header className="page-head">
        <h1>Live view</h1>
        <span className="muted">Green box = recognised, amber box = unknown</span>
      </header>
      <div className="live-grid">
        {cameras.length ? cameras.map((c) => <LiveCanvas key={c.id} camId={c.id} name={c.name} paused={c.paused} quality="large" onToggle={() => toggle(c)} />) : (
          <div className="empty"><b>No cameras found yet.</b><br />Plug in a USB camera, or add a network camera under Settings.</div>
        )}
      </div>
    </section>
  );
}
