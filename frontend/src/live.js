// One WebSocket shared by the whole app. It receives video frames + face boxes for every camera
// we are watching. If the connection drops it reconnects by itself.
import { wsUrl } from "./api";

async function decodeFrame(bytes) {
  const blob = new Blob([bytes], { type: "image/jpeg" });
  if (typeof createImageBitmap === "function") return createImageBitmap(blob);   // decodes off the main thread
  return new Promise((resolve, reject) => {                                      // older browsers
    const img = new Image();
    const url = URL.createObjectURL(blob);
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = reject;
    img.src = url;
  });
}

class LiveSocket {
  constructor() {
    this.ws = null;
    this.subs = new Set();       // { cam, quality, onFrame, onDet }
    this.retry = 0;
    this.busy = new Set();       // cameras whose frame is being decoded right now
    this.pending = new Map();    // newest undecoded frame per camera (older ones are dropped)
    document.addEventListener("visibilitychange", () => this.sendSubs());   // stop video in hidden tabs
  }

  subscribe(cam, quality, onFrame, onDet) {
    const sub = { cam, quality, onFrame, onDet };
    this.subs.add(sub);
    this.open();
    this.sendSoon();
    return () => {
      this.subs.delete(sub);
      this.sendSoon();
      if (!this.subs.size) this.close();
    };
  }

  open() {
    if (this.ws || !this.subs.size) return;
    let ws;
    try { ws = new WebSocket(wsUrl()); } catch (_) { return this.scheduleRetry(); }
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => { this.retry = 0; this.sendSubs(); };
    ws.onmessage = (e) => this.onMessage(e.data);
    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      if (this.subs.size) this.scheduleRetry();
    };
  }

  close() {
    clearTimeout(this.retryTimer);
    const ws = this.ws;
    this.ws = null;
    if (ws) { ws.onclose = null; ws.close(); }
  }

  scheduleRetry() {
    clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => this.open(), Math.min(5000, 500 * 2 ** this.retry++));
  }

  sendSoon() {
    clearTimeout(this.sendTimer);
    this.sendTimer = setTimeout(() => this.sendSubs(), 30);
  }

  sendSubs() {
    if (!this.ws || this.ws.readyState !== 1) return;
    const sub = {};
    if (!document.hidden) for (const s of this.subs) if (sub[s.cam] !== "large") sub[s.cam] = s.quality;
    this.ws.send(JSON.stringify({ sub }));
  }

  onMessage(data) {
    if (typeof data === "string") {
      let det;
      try { det = JSON.parse(data); } catch (_) { return; }
      for (const s of this.subs) if (s.cam === det.cam && s.onDet) s.onDet(det);
      return;
    }
    const bytes = new Uint8Array(data);
    const n = bytes[0];
    const cam = new TextDecoder().decode(bytes.subarray(1, 1 + n));
    this.handleFrame(cam, bytes.subarray(1 + n));
  }

  handleFrame(cam, jpeg) {
    if (this.busy.has(cam)) { this.pending.set(cam, jpeg); return; }   // newest wins
    this.busy.add(cam);
    decodeFrame(jpeg)
      .then((bmp) => {
        let taken = false;
        for (const s of this.subs) if (s.cam === cam && s.onFrame) { s.onFrame(bmp); taken = true; }
        if (!taken && bmp.close) bmp.close();
      })
      .catch(() => {})
      .finally(() => {
        this.busy.delete(cam);
        const next = this.pending.get(cam);
        if (next) { this.pending.delete(cam); this.handleFrame(cam, next); }
      });
  }
}

export const liveSocket = new LiveSocket();
