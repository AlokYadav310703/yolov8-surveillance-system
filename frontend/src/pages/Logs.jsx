import { useState } from "react";
import { api, assetUrl } from "../api";
import { fmtTime, usePoll, useToast } from "../hooks";

const PAGE = 50;

function rangeStart(range) {
  const now = Date.now() / 1000;
  if (range === "1h") return now - 3600;
  if (range === "7d") return now - 7 * 86400;
  if (range === "today") return new Date().setHours(0, 0, 0, 0) / 1000;
  return null;
}

export default function Logs({ cameras }) {
  const toast = useToast();
  const [person, setPerson] = useState("");
  const [camera, setCamera] = useState("");
  const [range, setRange] = useState("today");
  const [offset, setOffset] = useState(0);

  const [people] = usePoll(() => api("/api/people"), 10000);
  const query = () => {
    const q = new URLSearchParams();
    if (person) q.set("person", person);
    if (camera) q.set("camera", camera);
    const start = rangeStart(range);
    if (start) q.set("start", start);
    return q;
  };
  const [data, reload] = usePoll(() => {
    const q = query();
    q.set("limit", PAGE);
    q.set("offset", offset);
    return api("/api/logs?" + q);
  }, 4000, [person, camera, range, offset]);

  const change = (setter) => (e) => { setter(e.target.value); setOffset(0); };
  const total = data ? data.total : 0;

  const clear = async () => {
    if (!window.confirm("Delete the entire activity log and all saved face snapshots? This cannot be undone.")) return;
    try { await api("/api/logs", { method: "DELETE" }); toast("Log cleared"); setOffset(0); reload(); }
    catch (e) { toast(e.message, true); }
  };

  return (
    <section>
      <header className="page-head">
        <h1>Activity log</h1>
        <span className="muted">{data ? `${total} entr${total === 1 ? "y" : "ies"}` : ""}</span>
      </header>

      <div className="panel filters">
        <label>Person
          <select value={person} onChange={change(setPerson)}>
            <option value="">Everyone</option>
            <option value="Unknown">Unknown</option>
            {(people || []).map((p) => <option key={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label>Camera
          <select value={camera} onChange={change(setCamera)}>
            <option value="">All cameras</option>
            {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>When
          <select value={range} onChange={change(setRange)}>
            <option value="today">Today</option>
            <option value="1h">Last hour</option>
            <option value="7d">Last 7 days</option>
            <option value="all">All time</option>
          </select>
        </label>
        <span className="spacer" />
        <a className="btn" href={assetUrl("/api/logs/export.csv?" + query())}>Export CSV</a>
        <button className="btn danger" onClick={clear}>Clear log</button>
      </div>

      <div className="panel table-wrap">
        <table>
          <thead><tr><th>Face</th><th>Person</th><th>Camera</th><th>Time</th><th className="num">Match</th></tr></thead>
          <tbody>
            {data && data.items.length === 0 && (
              <tr><td colSpan={5} className="muted" style={{ padding: 24 }}>No entries for these filters yet.</td></tr>
            )}
            {(data ? data.items : []).map((r) => (
              <tr key={r.id}>
                <td>{r.snapshot ? <img className="face" src={assetUrl(`/snapshots/${r.snapshot}`)} alt="" /> : <span className="face" />}</td>
                <td className={r.person_id == null ? "tag-unk" : ""}>{r.person_name}</td>
                <td>{r.camera_name}</td>
                <td>{fmtTime(r.ts)}</td>
                <td className="num">{r.person_id == null || r.similarity == null ? "–" : Math.round(r.similarity * 100) + "%"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="pager">
          <button className="btn small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
          <span className="muted">{total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : ""}</span>
          <button className="btn small" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</button>
        </div>
      </div>
    </section>
  );
}
