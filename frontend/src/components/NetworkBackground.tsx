import { useEffect, useRef } from "react";

interface Dot {
  x: number; y: number;
  vx: number; vy: number;
  r: number;
  ox: number; oy: number; // spawn origin — gentle home spring
}

const COUNT         = 58;
const HOVER_R       = 65;
const ATTRACT       = 0.055;
const DAMPING       = 0.983;
const MAX_SPD       = 0.30;
const MIN_NODE_SEP  = 82;
const DRIFT_NOISE   = 0.005;
const HOME_SPRING   = 0.00018; // very gentle pull toward spawn point
const K_NEIGHBORS   = 4;       // neighbors per node for fixed triangulation

// Side-length thresholds for smooth fade
const EDGE_FADE_IN  = 150;
const EDGE_FADE_OUT = 265;
const TRI_FADE_IN   = 170;
const TRI_FADE_OUT  = 290;

function ptSegDist(
  px: number, py: number,
  ax: number, ay: number,
  bx: number, by: number
): number {
  const dx = bx - ax, dy = by - ay;
  const len2 = dx * dx + dy * dy;
  if (!len2) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

function edgeFade(d: number): number {
  if (d >= EDGE_FADE_OUT) return 0;
  if (d <= EDGE_FADE_IN)  return 1;
  return 1 - (d - EDGE_FADE_IN) / (EDGE_FADE_OUT - EDGE_FADE_IN);
}

function triFade(maxSide: number): number {
  if (maxSide >= TRI_FADE_OUT) return 0;
  if (maxSide <= TRI_FADE_IN)  return 1;
  return 1 - (maxSide - TRI_FADE_IN) / (TRI_FADE_OUT - TRI_FADE_IN);
}

export function NetworkBackground() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;
    if (!ctx) return;

    let W = window.innerWidth;
    let H = window.innerHeight;
    canvas.width = W;
    canvas.height = H;

    const mouse = { x: -9999, y: -9999 };
    let hovI = -1, hovJ = -1;
    let rafId: number;

    // ── Spawn dots with guaranteed minimum separation ────────────────────────
    const dots: Dot[] = [];
    let attempts = 0;
    while (dots.length < COUNT && attempts < COUNT * 60) {
      attempts++;
      const x = Math.random() * W;
      const y = Math.random() * H;
      if (dots.every(d => Math.hypot(d.x - x, d.y - y) >= MIN_NODE_SEP)) {
        dots.push({
          x, y, ox: x, oy: y,
          vx: (Math.random() - 0.5) * 0.16,
          vy: (Math.random() - 0.5) * 0.16,
          r: Math.random() * 1.1 + 1.1,
        });
      }
    }

    // ── Build fixed triangulation from initial positions ─────────────────────
    // For each node, find K nearest neighbors.
    // Edges: each neighbor pair. Triangles: when two of a node's neighbors
    // are also neighbors of each other. Topology is frozen — nodes only move.

    const neighbors: number[][] = dots.map((d, i) =>
      dots
        .map((d2, j) => [j, Math.hypot(d.x - d2.x, d.y - d2.y)] as [number, number])
        .filter(([j]) => j !== i)
        .sort(([, a], [, b]) => a - b)
        .slice(0, K_NEIGHBORS)
        .map(([j]) => j)
    );

    const edgeSet = new Set<string>();
    const triSet  = new Set<string>();
    const edges: [number, number][] = [];
    const triangles: [number, number, number][] = [];

    for (let i = 0; i < dots.length; i++) {
      for (let a = 0; a < neighbors[i].length; a++) {
        const j = neighbors[i][a];
        const ek = `${Math.min(i, j)},${Math.max(i, j)}`;
        if (!edgeSet.has(ek)) {
          edgeSet.add(ek);
          edges.push([Math.min(i, j), Math.max(i, j)]);
        }
        for (let b = a + 1; b < neighbors[i].length; b++) {
          const k = neighbors[i][b];
          if (neighbors[j].includes(k) || neighbors[k].includes(j)) {
            const tri = [i, j, k].sort((x, y) => x - y) as [number, number, number];
            const tk = tri.join(",");
            if (!triSet.has(tk)) {
              triSet.add(tk);
              triangles.push(tri);
            }
          }
        }
      }
    }

    // ── Render loop ──────────────────────────────────────────────────────────
    function frame() {
      ctx.clearRect(0, 0, W, H);

      // Hover: nearest fixed edge to mouse
      let bestD = HOVER_R, bi = -1, bj = -1;
      for (const [i, j] of edges) {
        const d = ptSegDist(mouse.x, mouse.y, dots[i].x, dots[i].y, dots[j].x, dots[j].y);
        if (d < bestD) { bestD = d; bi = i; bj = j; }
      }
      hovI = bi; hovJ = bj;

      // Physics
      for (let n = 0; n < dots.length; n++) {
        const d = dots[n];

        d.vx += (Math.random() - 0.5) * DRIFT_NOISE;
        d.vy += (Math.random() - 0.5) * DRIFT_NOISE;

        // Gentle home spring
        d.vx += (d.ox - d.x) * HOME_SPRING;
        d.vy += (d.oy - d.y) * HOME_SPRING;

        // Mouse attract on hovered edge nodes
        if (hovI >= 0 && (n === hovI || n === hovJ)) {
          const ex = mouse.x - d.x, ey = mouse.y - d.y;
          const dist = Math.hypot(ex, ey) || 1;
          if (dist > 55) {
            const factor = Math.min(1, (dist - 55) / 80);
            d.vx += (ex / dist) * ATTRACT * factor;
            d.vy += (ey / dist) * ATTRACT * factor;
          } else {
            d.vx -= (ex / dist) * ATTRACT * 0.5;
            d.vy -= (ey / dist) * ATTRACT * 0.5;
          }
        }

        d.vx *= DAMPING; d.vy *= DAMPING;
        const spd = Math.hypot(d.vx, d.vy);
        if (spd > MAX_SPD) { d.vx = d.vx / spd * MAX_SPD; d.vy = d.vy / spd * MAX_SPD; }
        d.x += d.vx; d.y += d.vy;
        if (d.x < 0) { d.x = 0; d.vx = Math.abs(d.vx); }
        if (d.x > W) { d.x = W; d.vx = -Math.abs(d.vx); }
        if (d.y < 0) { d.y = 0; d.vy = Math.abs(d.vy); }
        if (d.y > H) { d.y = H; d.vy = -Math.abs(d.vy); }
      }

      // Global repulsion — no node pair collapses
      for (let i = 0; i < dots.length; i++) {
        for (let j = i + 1; j < dots.length; j++) {
          const dx = dots[i].x - dots[j].x;
          const dy = dots[i].y - dots[j].y;
          const dist = Math.hypot(dx, dy) || 1;
          if (dist < MIN_NODE_SEP) {
            const f = (MIN_NODE_SEP - dist) / MIN_NODE_SEP * 0.07;
            dots[i].vx += (dx / dist) * f;
            dots[i].vy += (dy / dist) * f;
            dots[j].vx -= (dx / dist) * f;
            dots[j].vy -= (dy / dist) * f;
          }
        }
      }

      // Draw triangles — fixed topology, opacity driven by current max side length
      for (const [i, j, k] of triangles) {
        const sij = Math.hypot(dots[i].x - dots[j].x, dots[i].y - dots[j].y);
        const sjk = Math.hypot(dots[j].x - dots[k].x, dots[j].y - dots[k].y);
        const sik = Math.hypot(dots[i].x - dots[k].x, dots[i].y - dots[k].y);
        const a = triFade(Math.max(sij, sjk, sik));
        if (a <= 0) continue;

        const triHov = hovI >= 0 && (
          i === hovI || i === hovJ ||
          j === hovI || j === hovJ ||
          k === hovI || k === hovJ
        );

        const cx = (dots[i].x + dots[j].x + dots[k].x) / 3;
        const cy = (dots[i].y + dots[j].y + dots[k].y) / 3;
        const rr = Math.max(
          Math.hypot(dots[i].x - cx, dots[i].y - cy),
          Math.hypot(dots[j].x - cx, dots[j].y - cy),
          Math.hypot(dots[k].x - cx, dots[k].y - cy)
        ) || 1;

        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, rr);
        if (triHov) {
          grad.addColorStop(0,    `rgba(56,189,248,${+(0.20 * a).toFixed(3)})`);
          grad.addColorStop(0.55, `rgba(56,189,248,${+(0.08 * a).toFixed(3)})`);
          grad.addColorStop(1,     "rgba(56,189,248,0)");
        } else {
          grad.addColorStop(0,   `rgba(56,189,248,${+(0.058 * a).toFixed(3)})`);
          grad.addColorStop(0.5, `rgba(56,189,248,${+(0.022 * a).toFixed(3)})`);
          grad.addColorStop(1,    "rgba(56,189,248,0)");
        }

        ctx.beginPath();
        ctx.moveTo(dots[i].x, dots[i].y);
        ctx.lineTo(dots[j].x, dots[j].y);
        ctx.lineTo(dots[k].x, dots[k].y);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();
      }

      // Draw edges — fixed topology, opacity driven by current length
      for (const [i, j] of edges) {
        const dist = Math.hypot(dots[i].x - dots[j].x, dots[i].y - dots[j].y);
        const a = edgeFade(dist);
        if (a <= 0) continue;

        const ijHov     = (i === hovI && j === hovJ) || (i === hovJ && j === hovI);
        const iInvolved = i === hovI || i === hovJ;
        const jInvolved = j === hovI || j === hovJ;

        ctx.beginPath();
        ctx.moveTo(dots[i].x, dots[i].y);
        ctx.lineTo(dots[j].x, dots[j].y);
        if (ijHov) {
          ctx.strokeStyle = `rgba(148,215,255,${+Math.min(a * 0.85 + 0.15, 1).toFixed(3)})`;
          ctx.lineWidth = 1.8;
        } else if (iInvolved || jInvolved) {
          ctx.strokeStyle = `rgba(96,165,250,${+(a * 0.55 + 0.08).toFixed(3)})`;
          ctx.lineWidth = 0.9;
        } else {
          ctx.strokeStyle = `rgba(56,189,248,${+(a * 0.18).toFixed(3)})`;
          ctx.lineWidth = 0.5;
        }
        ctx.stroke();
      }

      // Draw nodes
      for (let n = 0; n < dots.length; n++) {
        const d = dots[n];
        const hov = hovI >= 0 && (n === hovI || n === hovJ);
        if (hov) {
          const g = ctx.createRadialGradient(d.x, d.y, 0, d.x, d.y, d.r * 6);
          g.addColorStop(0, "rgba(148,215,255,0.4)");
          g.addColorStop(1, "rgba(56,189,248,0)");
          ctx.beginPath();
          ctx.arc(d.x, d.y, d.r * 6, 0, Math.PI * 2);
          ctx.fillStyle = g;
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(d.x, d.y, hov ? d.r * 1.6 : d.r, 0, Math.PI * 2);
        ctx.fillStyle = hov ? "rgba(205,240,255,0.95)" : "rgba(96,165,250,0.65)";
        ctx.fill();
      }

      rafId = requestAnimationFrame(frame);
    }

    const onMove   = (e: MouseEvent) => { mouse.x = e.clientX; mouse.y = e.clientY; };
    const onLeave  = () => { mouse.x = -9999; mouse.y = -9999; };
    const onResize = () => {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W; canvas.height = H;
    };

    window.addEventListener("mousemove",  onMove);
    window.addEventListener("mouseleave", onLeave);
    window.addEventListener("resize",     onResize);
    frame();

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("mousemove",  onMove);
      window.removeEventListener("mouseleave", onLeave);
      window.removeEventListener("resize",     onResize);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      style={{
        position: "fixed",
        inset: 0,
        width: "100vw",
        height: "100vh",
        zIndex: 0,
        display: "block",
        background: "linear-gradient(160deg, #020c1b 0%, #020f24 55%, #010810 100%)",
        pointerEvents: "none",
      }}
    />
  );
}
