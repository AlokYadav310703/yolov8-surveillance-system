import { useState } from "react";
import { getApiBase, getKey, saveConnection } from "../api";

export default function ConnectScreen({ reason, needsKey }) {
  const [url, setUrl] = useState(getApiBase());
  const [key, setKey] = useState(getKey());
  const save = (e) => {
    e.preventDefault();
    saveConnection(url, key);
    location.reload();
  };
  return (
    <div className="connect">
      <form className="panel connect-card" onSubmit={save}>
        <h1>Connect to FaceWatch</h1>
        <p className="hint">{reason}</p>
        <label className="field">Backend address
          <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:8000" />
        </label>
        <label className="field">Access key {needsKey ? "" : "(only if the backend asks for one)"}
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" />
        </label>
        <button className="btn primary" type="submit">Connect</button>
      </form>
    </div>
  );
}
