import { useCallback, useEffect, useRef, useState } from "react";
import { api, getApiBase } from "./api";
import { ToastContext, usePoll } from "./hooks";
import Sidebar from "./components/Sidebar";
import ConnectScreen from "./components/ConnectScreen";
import Dashboard from "./pages/Dashboard";
import Live from "./pages/Live";
import People from "./pages/People";
import Logs from "./pages/Logs";
import Settings from "./pages/Settings";

const PAGE_IDS = ["dashboard", "live", "people", "logs", "settings"];
const fromHash = () => (PAGE_IDS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "dashboard");

export default function App() {
  const [page, setPage] = useState(fromHash);
  const [conn, setConn] = useState({ state: "checking" });
  const [toast, setToast] = useState(null);
  const toastTimer = useRef();

  const notify = useCallback((message, bad = false) => {
    setToast({ message, bad });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4200);
  }, []);

  useEffect(() => {
    const onHash = () => setPage(fromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Check the backend once at start-up: reachable? needs a key?
  useEffect(() => {
    (async () => {
      try {
        const health = await api("/api/health");
        if (health.auth_required) await api("/api/settings");     // 401 here means the key is missing/wrong
        setConn({ state: "ok", detector: health.detector });
      } catch (e) {
        setConn({ state: e.status === 401 ? "auth" : "down" });
      }
    })();
  }, []);

  const connected = conn.state === "ok";
  const [camData, reloadCameras] = usePoll(() => (connected ? api("/api/cameras") : Promise.reject()), 2500, [connected]);
  const cameras = (camData && camData.cameras) || [];

  const go = (id) => { location.hash = id; setPage(id); };

  if (conn.state === "checking") return <div className="connect"><p className="muted">Connecting…</p></div>;
  if (conn.state === "down")
    return <ConnectScreen reason={`Cannot reach the backend at ${getApiBase()}. Is it running? You can also point FaceWatch at a different address.`} />;
  if (conn.state === "auth")
    return <ConnectScreen needsKey reason="This backend is protected. Enter its access key." />;

  return (
    <ToastContext.Provider value={notify}>
      <div className="shell">
        <Sidebar page={page} onNavigate={go} cameras={cameras} detector={conn.detector} />
        <main>
          {page === "dashboard" && <Dashboard cameras={cameras} reload={reloadCameras} />}
          {page === "live" && <Live cameras={cameras} reload={reloadCameras} />}
          {page === "people" && <People cameras={cameras} />}
          {page === "logs" && <Logs cameras={cameras} />}
          {page === "settings" && <Settings cameras={cameras} reload={reloadCameras} />}
        </main>
      </div>
      <div className={"toast" + (toast ? " show" : "") + (toast && toast.bad ? " bad" : "")} role="status">
        {toast && toast.message}
      </div>
    </ToastContext.Provider>
  );
}
