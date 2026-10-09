import { api, assetUrl } from "../api";
import { ago, fmtTime, useCameraToggle, usePoll } from "../hooks";
import LiveCanvas from "../components/LiveCanvas";

function Bars({ rows, empty }) {
  if (!rows.length) return <span className="muted">{empty}</span>;
  const max = Math.max(...rows.map((r) => r.n));
  return (
    <div className="bars">
      {rows.map((r) => (
        <div className="bar-row" key={r.name}>
          <span className="name" title={r.name}>{r.name}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(r.n / max) * 100}%` }} /></div>
          <span className="v">{r.n}</span>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard({ cameras, reload }) {
  const toggle = useCameraToggle(reload);
  const [s] = usePoll(() => api("/api/stats"), 3000);
  const max = s ? Math.max(1, ...s.hourly.map((h) => h.known + h.unknown)) : 1;
  const pad = (n) => String(n).padStart(2, "0");

  return (
    <section>
      <header className="page-head"><h1>Dashboard</h1></header>

      <div className="cam-strip">
        {cameras.length ? cameras.map((c) => <LiveCanvas key={c.id} camId={c.id} name={c.name} paused={c.paused} quality="small" onToggle={() => toggle(c)} />) : (
          <div className="empty"><b>No cameras found yet.</b><br />Plug in a USB camera and it appears here within about 10 seconds. For an IP camera or a video file, add it under Settings.</div>
        )}
      </div>

      {s && (
        <>
          <div className="stats">
            <div className="stat"><div className="n">{s.cameras_online}<span className="muted"> / {s.cameras_total}</span></div><div className="l">Cameras online</div></div>
            <div className="stat"><div className="n">{s.people}</div><div className="l">People enrolled</div></div>
            <div className="stat ok"><div className="n">{s.known_today}</div><div className="l">Recognised today</div></div>
            <div className="stat unk"><div className="n">{s.unknown_today}</div><div className="l">Unknown today</div></div>
            <div className="stat"><div className="n">{s.total_logs}</div><div className="l">Entries in log</div></div>
          </div>

          <div className="grid-2">
            <div className="panel">
              <h2>Sightings in the last 24 hours</h2>
              <div className="chart">
                {s.hourly.map((h, i) => (
                  <div className="col" key={i} title={`${pad(h.hour)}:00 - ${h.known} recognised, ${h.unknown} unknown`}>
                    <div className="seg-u" style={{ height: `${(h.unknown / max) * 100}%` }} />
                    <div className="seg-k" style={{ height: `${(h.known / max) * 100}%` }} />
                    {i % 3 === 0 && <span className="tick">{pad(h.hour)}</span>}
                  </div>
                ))}
              </div>
              <div className="legend"><span><i className="sw known" />Recognised</span><span><i className="sw unknown" />Unknown</span></div>
            </div>
            <div className="panel">
              <h2>Latest sightings</h2>
              <div className="feed">
                {s.recent.length ? s.recent.map((r) => (
                  <div className="feed-item" key={r.id}>
                    {r.snapshot ? <img className="face" src={assetUrl(`/snapshots/${r.snapshot}`)} alt="" /> : <span className="face" />}
                    <div>
                      <div className={"who" + (r.person_id == null ? " unk" : "")}>{r.person_name}</div>
                      <div className="sub">{r.camera_name}</div>
                    </div>
                    <span className="when" title={fmtTime(r.ts)}>{ago(r.ts)}</span>
                  </div>
                )) : <span className="muted">Nothing seen yet. Add faces under People, then walk in front of a camera.</span>}
              </div>
            </div>
          </div>

          <div className="grid-2">
            <div className="panel"><h2>Sightings today by camera</h2><Bars rows={s.by_camera} empty="No sightings today." /></div>
            <div className="panel"><h2>Most seen today</h2><Bars rows={s.top_people} empty="No recognised people today." /></div>
          </div>
        </>
      )}
    </section>
  );
}
