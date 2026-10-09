import { useEffect, useState } from "react";
import { api, assetUrl, sendJson } from "../api";
import { ago, usePoll, useToast } from "../hooks";

export default function People({ cameras }) {
  const toast = useToast();
  const [people, reload] = usePoll(() => api("/api/people"), 5000);
  const [name, setName] = useState("");
  const [files, setFiles] = useState([]);
  const [cam, setCam] = useState("");
  const [busy, setBusy] = useState(false);
  const online = cameras.filter((c) => c.online);

  useEffect(() => { if (!online.find((c) => c.id === cam)) setCam(online[0] ? online[0].id : ""); }, [cameras]);   // eslint-disable-line

  const upload = async () => {
    if (!name.trim()) return toast("Enter a name first.", true);
    if (!files.length) return toast("Choose at least one photo.", true);
    const fd = new FormData();
    fd.append("name", name.trim());
    files.forEach((f) => fd.append("files", f));
    setBusy(true);
    try {
      const r = await api("/api/people", { method: "POST", body: fd });
      toast(`Added ${r.added} photo${r.added === 1 ? "" : "s"} for ${r.name}` + (r.skipped ? ` (${r.skipped} had no clear face)` : ""));
      setName(""); setFiles([]); document.getElementById("photoInput").value = "";
      reload();
    } catch (e) { toast(e.message, true); }
    setBusy(false);
  };

  const capture = async () => {
    if (!name.trim()) return toast("Enter a name first.", true);
    if (!cam) return toast("No camera is online.", true);
    setBusy(true);
    try {
      const r = await sendJson("/api/people/from-camera", { name: name.trim(), camera_id: cam });
      toast(`Captured ${r.name}. Capture again from another angle for better accuracy.`);
      reload();
    } catch (e) { toast(e.message, true); }
    setBusy(false);
  };

  const remove = async (p) => {
    if (!window.confirm(`Remove ${p.name}? Their face data is deleted. Past log entries stay.`)) return;
    try { await api(`/api/people/${p.id}`, { method: "DELETE" }); toast("Removed " + p.name); reload(); }
    catch (e) { toast(e.message, true); }
  };

  return (
    <section>
      <header className="page-head"><h1>People</h1></header>
      <div className="people-layout">
        <div className="panel">
          <h2>Add a face</h2>
          <label className="field">Name
            <input type="text" maxLength={60} placeholder="e.g. Priya Shah" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">Photos
            <input id="photoInput" type="file" accept="image/*" multiple onChange={(e) => setFiles([...e.target.files])} />
          </label>
          <p className="hint">Use clear, front-facing photos with one person. Three to five photos from different angles give the best results. Adding photos to an existing name improves that person.</p>
          <button className="btn primary" disabled={busy} onClick={upload}>Add from photos</button>
          <div className="or"><span>or</span></div>
          <label className="field">Take a picture with a camera
            <select value={cam} onChange={(e) => setCam(e.target.value)}>
              {online.length ? online.map((c) => <option key={c.id} value={c.id}>{c.name}</option>) : <option value="">No camera online</option>}
            </select>
          </label>
          <button className="btn" disabled={busy} onClick={capture}>Capture face from camera</button>
        </div>

        <div className="people-grid">
          {people && people.length === 0 && (
            <div className="empty"><b>No faces added yet.</b><br />Enter a name and choose a photo to teach FaceWatch who to look for.</div>
          )}
          {(people || []).map((p) => (
            <div className="person" key={p.id}>
              <img src={assetUrl(`/api/people/${p.id}/photo`)} alt="" onError={(e) => (e.target.style.visibility = "hidden")} />
              <div className="body">
                <div className="nm" title={p.name}>{p.name}</div>
                <div className="sub">{p.photos} photo{p.photos === 1 ? "" : "s"}<br />{p.last_seen ? `Seen ${ago(p.last_seen)} · ${p.last_camera}` : "Not seen yet"}</div>
                <button className="btn danger small" onClick={() => remove(p)}>Remove</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
