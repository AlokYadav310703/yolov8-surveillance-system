import { useEffect, useRef, useState } from "react";
import { liveSocket } from "../live";

const KNOWN = "#6ec83c";
const UNKNOWN = "#f5960a";

// Match new face boxes to the ones already on screen so they glide instead of jumping.
function updateBoxes(state, det, now) {
  const used = new Set();
  for (const f of det.faces) {
    let best = null, bestDist = Infinity;
    for (const b of state.boxes) {
      if (used.has(b)) continue;
      const d = Math.hypot(b.tx + b.tw / 2 - (f.x + f.w / 2), b.ty + b.th / 2 - (f.y + f.h / 2));
      if (d < bestDist && d < Math.max(b.tw, b.th)) { best = b; bestDist = d; }
    }
    if (best) {
      Object.assign(best, { tx: f.x, ty: f.y, tw: f.w, th: f.h, name: f.name, sim: f.sim, seen: now });
      used.add(best);
    } else {
      const nb = { x: f.x, y: f.y, w: f.w, h: f.h, tx: f.x, ty: f.y, tw: f.w, th: f.h, name: f.name, sim: f.sim, seen: now };
      state.boxes.push(nb);
      used.add(nb);
    }
  }
  state.srcW = det.w;
}

export default function LiveCanvas({ camId, name, quality = "small", paused = false, onToggle }) {
  const canvasRef = useRef(null);
  const [info, setInfo] = useState({ online: true, faces: 0, fps: 0 });
  const [hasVideo, setHasVideo] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const s = { bmp: null, boxes: [], srcW: 0, dirty: false, raf: 0, lastInfo: 0, hasVideo: false };
    setHasVideo(false);

    const unsubscribe = liveSocket.subscribe(
      camId,
      quality,
      (bmp) => {
        if (s.bmp && s.bmp.close) s.bmp.close();
        s.bmp = bmp;
        s.dirty = true;
        if (!s.hasVideo) { s.hasVideo = true; setHasVideo(true); }
      },
      (det) => {
        const now = performance.now();
        updateBoxes(s, det, now);
        if (now - s.lastInfo > 500) {                 // don't re-render the page 10x per second
          s.lastInfo = now;
          setInfo({ online: det.online, faces: det.faces.length, fps: det.fps });
        }
      }
    );

    const draw = () => {
      s.raf = requestAnimationFrame(draw);
      const bmp = s.bmp;
      if (!bmp) return;
      const now = performance.now();
      const before = s.boxes.length;
      s.boxes = s.boxes.filter((b) => now - b.seen < 300);   // face left the picture
      if (s.boxes.length !== before) s.dirty = true;

      let moving = false;                                    // ease each box towards its newest position
      for (const b of s.boxes) {
        for (const [cur, target] of [["x", "tx"], ["y", "ty"], ["w", "tw"], ["h", "th"]]) {
          const diff = b[target] - b[cur];
          if (Math.abs(diff) > 0.4) { b[cur] += diff * 0.35; moving = true; } else b[cur] = b[target];
        }
      }
      if (!s.dirty && !moving) return;
      s.dirty = false;

      if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
        canvas.width = bmp.width;
        canvas.height = bmp.height;
      }
      ctx.drawImage(bmp, 0, 0);
      const k = bmp.width / (s.srcW || bmp.width);
      const font = Math.max(12, Math.round(bmp.width / 48));
      ctx.lineWidth = Math.max(2, Math.round(bmp.width / 320));
      ctx.font = `600 ${font}px system-ui, sans-serif`;
      ctx.textBaseline = "middle";
      for (const b of s.boxes) {
        const color = b.name ? KNOWN : UNKNOWN;
        const x = b.x * k, y = b.y * k, w = b.w * k, h = b.h * k;
        ctx.strokeStyle = color;
        ctx.strokeRect(x, y, w, h);
        const label = b.name ? `${b.name}  ${Math.round(b.sim * 100)}%` : "Unknown";
        const tw = ctx.measureText(label).width + 12;
        const th = font + 8;
        const ty = y - th < 0 ? y : y - th;
        ctx.fillStyle = color;
        ctx.fillRect(x, ty, tw, th);
        ctx.fillStyle = "#fff";
        ctx.fillText(label, x + 6, ty + th / 2 + 1);
      }
    };
    s.raf = requestAnimationFrame(draw);

    return () => {
      unsubscribe();
      cancelAnimationFrame(s.raf);
      if (s.bmp && s.bmp.close) s.bmp.close();
    };
  }, [camId, quality]);

  return (
    <div className="cam-tile">
      <div className="cv">
        <canvas ref={canvasRef} />
        {paused ? (
          <div className="cv-msg solid">Camera stopped</div>
        ) : (!hasVideo || !info.online) && (
          <div className="cv-msg">{info.online ? "Connecting…" : "Offline - reconnecting…"}</div>
        )}
      </div>
      <div className="cam-meta">
        <span className={"dot " + (paused ? "" : info.online ? "on" : "off")} />
        <b>{name}</b>
        <span className="faces">
          {!paused && info.online ? `${info.faces ? info.faces + (info.faces === 1 ? " face · " : " faces · ") : ""}${info.fps} fps` : ""}
        </span>
        {onToggle && (
          <button className={"tile-btn" + (paused ? " start" : "")} onClick={onToggle}
                  title={paused ? "Start this camera" : "Stop this camera and release it"}>
            {paused ? "Start" : "Stop"}
          </button>
        )}
      </div>
    </div>
  );
}
