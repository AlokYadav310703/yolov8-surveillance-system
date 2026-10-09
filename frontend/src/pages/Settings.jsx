import { useEffect, useState } from "react";
import { api, getApiBase, getKey, saveConnection, sendJson } from "../api";
import { useCameraToggle, useToast } from "../hooks";

export default function Settings({ cameras, reload }) {
  const toast = useToast();
  const toggle = useCameraToggle(reload);
  const [form, setForm] = useState(null);
  const [info, setInfo] = useState({ detector: "", recognizer: "" });
  const [net, setNet] = useState({ name: "", source: "" });
  const [scanning, setScanning] = useState(false);
  const [conn, setConn] = useState({ url: getApiBase(), key: getKey() });

  useEffect(() => {
    api("/api/settings").then((s) => {
      setForm({ threshold: s.threshold, cooldown: s.cooldown, log_unknown: s.log_unknown });
      setInfo({ detector: s.detector, recognizer: s.recognizer });
    }).catch(() => {});
  }, []);

  const save = async () => {
    try {
      await sendJson("/api/settings", { threshold: +form.threshold, cooldown: +form.cooldown || 10, log_unknown: form.log_unknown }, "PUT");
      toast("Settings saved");
    } catch (e) { toast(e.message, true); }
  };
  const rename = async (c) => {
    const name = window.prompt("Camera name", c.name);
    if (!name || !name.trim()) return;
    try { await sendJson(`/api/cameras/${c.id}`, { name }, "PUT"); reload(); } catch (e) { toast(e.message, true); }
  };
  const remove = async (c) => {
    if (!window.confirm(`Remove camera "${c.name}"?`)) return;
    try { await api(`/api/cameras/${c.id}`, { method: "DELETE" }); reload(); } catch (e) { toast(e.message, true); }
  };
  const rescan = async () => {
    setScanning(true);
    try { const r = await api("/api/cameras/rescan", { method: "POST" }); reload(); toast(`${r.cameras.length} camera${r.cameras.length === 1 ? "" : "s"} found`); }
    catch (e) { toast(e.message, true); }
    setScanning(false);
  };
  const addNet = async () => {
    try { await sendJson("/api/cameras", net); setNet({ name: "", source: "" }); toast("Camera added"); reload(); }
    catch (e) { toast(e.message, true); }
  };

  return (
    <section>
      <header className="page-head"><h1>Settings</h1></header>
      <div className="grid-2">
        <div className="panel">
          <h2>Recognition</h2>
          {form && (
            <>
              <label className="field">Match strictness <b>{Number(form.threshold).toFixed(2)}</b>
                <input type="range" min="0.2" max="0.8" step="0.01" value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })} />
              </label>
              <p className="hint">How alike a face must be to count as a match. Raise it if the wrong people are being named. Lower it if the right people show up as Unknown.</p>
              <label className="field">Log the same person again after (seconds)
                <input type="number" min="1" max="3600" value={form.cooldown} onChange={(e) => setForm({ ...form, cooldown: e.target.value })} />
              </label>
              <label className="check"><input type="checkbox" checked={form.log_unknown} onChange={(e) => setForm({ ...form, log_unknown: e.target.checked })} /> Also log faces that match nobody</label>
              <button className="btn primary" onClick={save}>Save settings</button>
              <p className="hint" style={{ marginTop: 14 }}>Face detector: {info.detector}. Face recognition: {info.recognizer}.</p>
            </>
          )}

          <div className="or"><span>backend connection</span></div>
          <label className="field">Backend address
            <input type="text" value={conn.url} onChange={(e) => setConn({ ...conn, url: e.target.value })} />
          </label>
          <label className="field">Access key
            <input type="password" value={conn.key} autoComplete="off" onChange={(e) => setConn({ ...conn, key: e.target.value })} />
          </label>
          <button className="btn" onClick={() => { saveConnection(conn.url, conn.key); location.reload(); }}>Save and reconnect</button>
        </div>

        <div className="panel">
          <h2>Cameras</h2>
          <p className="hint">USB cameras are found automatically, a few seconds after you plug them in.</p>
          <div className="cam-list">
            {cameras.length === 0 && <span className="muted">No cameras found.</span>}
            {cameras.map((c) => (
              <div className="cam-row" key={c.id}>
                <span className={"dot " + (c.paused ? "" : c.online ? "on" : "off")} />
                <div className="info"><b>{c.name}</b><span>{c.source}{c.paused ? " · stopped" : c.online ? "" : " · offline"}</span></div>
                <button className="btn small" onClick={() => toggle(c)}>{c.paused ? "Start" : "Stop"}</button>
                <button className="btn small" onClick={() => rename(c)}>Rename</button>
                {c.kind === "network" && <button className="btn small danger" onClick={() => remove(c)}>Remove</button>}
              </div>
            ))}
          </div>
          <button className="btn" disabled={scanning} onClick={rescan}>{scanning ? "Scanning…" : "Scan for cameras now"}</button>

          <div className="or"><span>network camera or video file</span></div>
          <label className="field">Name
            <input type="text" maxLength={60} placeholder="e.g. Front door" value={net.name} onChange={(e) => setNet({ ...net, name: e.target.value })} />
          </label>
          <label className="field">Stream address or file path
            <input type="text" placeholder="rtsp://user:password@192.168.1.20:554/stream1" value={net.source} onChange={(e) => setNet({ ...net, source: e.target.value })} />
          </label>
          <button className="btn" onClick={addNet}>Add camera</button>
        </div>
      </div>
    </section>
  );
}
