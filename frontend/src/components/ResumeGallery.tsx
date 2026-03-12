import { useEffect, useState } from "react";

interface GalleryItem {
  id: number;
  name: string;
  job: string;
  score: number;
  pdf: string;
  preview: string;
}

// ── Score badge ──────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const color  = score >= 85 ? "#4ade80" : score >= 70 ? "#60a5fa" : "#fbbf24";
  const label  = score >= 85 ? "Excellent fit" : score >= 70 ? "Strong match" : "Good match";
  return (
    <div style={{
      display: "flex", flexDirection: "column" as const, alignItems: "center", gap: 2,
      background: "rgba(2,8,22,0.88)", borderRadius: 10,
      border: `1.5px solid ${color}55`, padding: "8px 14px",
      backdropFilter: "blur(8px)",
    }}>
      <span style={{ fontSize: 24, fontWeight: 900, color, lineHeight: 1, letterSpacing: "-0.03em" }}>
        {score}
      </span>
      <span style={{
        fontSize: 9, fontWeight: 800, letterSpacing: "0.12em",
        color: color, opacity: 0.75,
        textTransform: "uppercase" as const,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      }}>
        {label}
      </span>
    </div>
  );
}

// ── Individual gallery card ───────────────────────────────────────────────────

function GalleryCard({
  item, isActive, onClick,
}: {
  item: GalleryItem;
  isActive: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      style={{
        position: "relative",
        width: 290,
        flexShrink: 0,
        cursor: "pointer",
        borderRadius: 14,
        overflow: "hidden",
        border: isActive
          ? "1.5px solid rgba(96,165,250,0.4)"
          : "1.5px solid rgba(255,255,255,0.09)",
        boxShadow: hovered
          ? "0 28px 72px rgba(0,0,0,0.75), 0 0 0 1px rgba(96,165,250,0.18)"
          : isActive
          ? "0 20px 56px rgba(0,0,0,0.65)"
          : "0 8px 28px rgba(0,0,0,0.45)",
        transform: hovered
          ? "translateY(-10px) scale(1.015)"
          : isActive
          ? "translateY(-4px)"
          : "none",
        transition: "transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1), box-shadow 0.22s, border-color 0.22s",
        background: "rgba(4,10,28,0.97)",
      }}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Resume preview — zoomed to top for quality thumbnail visibility */}
      <div style={{ position: "relative", width: "100%", paddingBottom: "129.4%" }}>
        <img
          src={item.preview}
          alt={`Resume preview — ${item.name}`}
          style={{
            position: "absolute", top: 0, left: 0,
            width: "100%", height: "100%",
            objectFit: "cover", objectPosition: "top center",
            display: "block",
          }}
          loading="lazy"
        />

        {/* Score badge */}
        <div style={{ position: "absolute", top: 12, right: 12, zIndex: 2 }}>
          <ScoreBadge score={item.score} />
        </div>

        {/* Hover reveal overlay */}
        <div style={{
          position: "absolute", inset: 0, zIndex: 3,
          background: "rgba(0,0,0,0.38)",
          display: "flex", alignItems: "center", justifyContent: "center",
          opacity: hovered ? 1 : 0,
          transition: "opacity 0.18s",
          pointerEvents: hovered ? "auto" : "none",
        }}>
          <div style={{
            background: "rgba(37,99,235,0.92)", borderRadius: 8,
            padding: "11px 22px", color: "#fff", fontWeight: 800,
            fontSize: 14, letterSpacing: "0.01em",
            boxShadow: "0 4px 18px rgba(37,99,235,0.5)",
          }}>
            View full resume ↗
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        padding: "14px 16px 16px",
        borderTop: "1px solid rgba(255,255,255,0.07)",
        background: "rgba(2,6,20,0.6)",
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#e2e8f0", marginBottom: 4, letterSpacing: "-0.01em" }}>
          {item.name}
        </div>
        <div style={{ fontSize: 11, color: "#64748b", lineHeight: 1.45 }}>
          {item.job}
        </div>
      </div>
    </div>
  );
}

// ── Lightbox ─────────────────────────────────────────────────────────────────

function Lightbox({
  item, items, onClose, onNav,
}: {
  item: GalleryItem;
  items: GalleryItem[];
  onClose: () => void;
  onNav: (item: GalleryItem) => void;
}) {
  const idx = items.findIndex(i => i.id === item.id);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && idx > 0) onNav(items[idx - 1]);
      if (e.key === "ArrowRight" && idx < items.length - 1) onNav(items[idx + 1]);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [idx, items, onClose, onNav]);

  const scoreColor = item.score >= 85 ? "#4ade80" : item.score >= 70 ? "#60a5fa" : "#fbbf24";

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 2000,
        background: "rgba(0,4,14,0.94)", backdropFilter: "blur(16px)",
        display: "flex", flexDirection: "column" as const,
        alignItems: "center", justifyContent: "flex-start",
        paddingTop: 56, paddingBottom: 80,
        overflowY: "auto",
      }}
      onClick={onClose}
    >
      {/* Modal card — iframe renders the full PDF page */}
      <div
        style={{
          position: "relative",
          width: "min(680px, 92vw)",
          borderRadius: 14,
          overflow: "hidden",
          boxShadow: "0 48px 120px rgba(0,0,0,0.8)",
          border: "1px solid rgba(255,255,255,0.12)",
          background: "#fff",
          aspectRatio: "8.5 / 11",
        }}
        onClick={e => e.stopPropagation()}
      >
        <iframe
          src={`${item.pdf}#toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
          title={`Resume — ${item.name}`}
          style={{ width: "100%", height: "100%", border: "none", display: "block" }}
        />
      </div>

      {/* Info strip (below image) */}
      <div
        style={{
          marginTop: 20,
          width: "min(680px, 92vw)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          padding: "14px 20px",
          background: "rgba(4,12,30,0.9)",
          borderRadius: 10,
          border: "1px solid rgba(255,255,255,0.1)",
          backdropFilter: "blur(12px)",
        }}
        onClick={e => e.stopPropagation()}
      >
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", marginBottom: 3 }}>
            {item.name}
          </div>
          <div style={{ fontSize: 12, color: "#64748b" }}>{item.job}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
          <div style={{ textAlign: "center" as const }}>
            <div style={{ fontSize: 22, fontWeight: 900, color: scoreColor, lineHeight: 1, letterSpacing: "-0.03em" }}>
              {item.score}
            </div>
            <div style={{ fontSize: 9, fontWeight: 700, color: scoreColor, opacity: 0.7, letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
              match
            </div>
          </div>
          <a
            href={item.pdf}
            download
            style={{
              padding: "9px 18px",
              background: "rgba(37,99,235,0.85)",
              border: "1.5px solid rgba(96,165,250,0.35)",
              borderRadius: 7,
              color: "#fff",
              fontSize: 13,
              fontWeight: 700,
              textDecoration: "none",
              letterSpacing: "0.01em",
            }}
            onClick={e => e.stopPropagation()}
          >
            Download PDF
          </a>
        </div>
      </div>

      {/* Navigation dots */}
      <div style={{
        display: "flex", gap: 8, marginTop: 18,
      }}>
        {items.map((it, i) => (
          <button
            key={it.id}
            style={{
              width: i === idx ? 24 : 8,
              height: 8,
              borderRadius: 100,
              background: i === idx ? "#3b82f6" : "rgba(255,255,255,0.2)",
              border: "none",
              cursor: "pointer",
              transition: "width 0.2s, background 0.2s",
              padding: 0,
            }}
            onClick={e => { e.stopPropagation(); onNav(it); }}
          />
        ))}
      </div>

      {/* Close button */}
      <button
        style={{
          position: "fixed", top: 16, right: 20, zIndex: 2100,
          width: 36, height: 36, borderRadius: "50%",
          background: "rgba(255,255,255,0.1)",
          border: "1px solid rgba(255,255,255,0.15)",
          color: "#94a3b8", fontSize: 16, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "background 0.15s",
        }}
        onClick={onClose}
      >
        ✕
      </button>

      {/* Side nav arrows */}
      {idx > 0 && (
        <button
          style={sArrow("left")}
          onClick={e => { e.stopPropagation(); onNav(items[idx - 1]); }}
        >
          ←
        </button>
      )}
      {idx < items.length - 1 && (
        <button
          style={sArrow("right")}
          onClick={e => { e.stopPropagation(); onNav(items[idx + 1]); }}
        >
          →
        </button>
      )}
    </div>
  );
}

function sArrow(side: "left" | "right"): React.CSSProperties {
  return {
    position: "fixed",
    top: "50%",
    [side]: 20,
    transform: "translateY(-50%)",
    zIndex: 2100,
    width: 44,
    height: 44,
    borderRadius: "50%",
    background: "rgba(255,255,255,0.08)",
    border: "1px solid rgba(255,255,255,0.14)",
    color: "#e2e8f0",
    fontSize: 18,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "background 0.15s",
  };
}

// ── Main gallery section ──────────────────────────────────────────────────────

export function ResumeGallery() {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [lightbox, setLightbox] = useState<GalleryItem | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);

  useEffect(() => {
    fetch("/gallery/manifest.json")
      .then(r => r.json())
      .then(setItems)
      .catch(() => {});
  }, []);

  if (!items.length) return null;

  function openLightbox(item: GalleryItem) {
    setLightbox(item);
    // sync lightbox position to active card
    setActiveIdx(items.findIndex(i => i.id === item.id));
  }

  return (
    <section style={sg.section}>
      {/* Atmospheric top edge glow */}
      <div style={sg.topGlow} />

      <div style={sg.inner}>
        {/* Section header */}
        <div style={sg.header}>
          <div style={sg.label}>Gallery</div>
          <h2 style={sg.heading}>
            Real resumes.<br />Real results.
          </h2>
          <p style={sg.sub}>
            Every resume below was generated by ApplyEasy — tailored to an actual job posting,
            grounded in real candidate experience, and scored by our matching engine.
          </p>
        </div>

        {/* Cards row */}
        <div style={sg.cardRow}>
          {items.map((item, i) => (
            <GalleryCard
              key={item.id}
              item={item}
              isActive={i === activeIdx}
              onClick={() => {
                if (i === activeIdx) {
                  openLightbox(item);
                } else {
                  setActiveIdx(i);
                }
              }}
            />
          ))}
        </div>

        {/* Nav dots + hint */}
        <div style={sg.navRow}>
          {items.map((_, i) => (
            <button
              key={i}
              style={{
                ...sg.dot,
                width: i === activeIdx ? 24 : 8,
                background: i === activeIdx ? "#3b82f6" : "rgba(255,255,255,0.2)",
              }}
              onClick={() => setActiveIdx(i)}
            />
          ))}
        </div>
        <div style={sg.hint}>Click any resume to preview it in full</div>
      </div>

      {/* Lightbox */}
      {lightbox && (
        <Lightbox
          item={lightbox}
          items={items}
          onClose={() => setLightbox(null)}
          onNav={item => setLightbox(item)}
        />
      )}
    </section>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const sg: Record<string, React.CSSProperties> = {
  section: {
    position: "relative",
    background: "rgba(0,3,12,0.85)",
    borderTop: "1px solid rgba(255,255,255,0.06)",
    padding: "96px 0 80px",
    overflow: "hidden",
  },
  topGlow: {
    position: "absolute",
    top: 0,
    left: "50%",
    transform: "translateX(-50%)",
    width: 800,
    height: 200,
    background: "radial-gradient(ellipse at 50% 0%, rgba(37,99,235,0.09) 0%, transparent 70%)",
    pointerEvents: "none",
  },
  inner: {
    position: "relative",
    zIndex: 1,
    maxWidth: 1300,
    margin: "0 auto",
    padding: "0 48px",
  },
  header: {
    marginBottom: 48,
  },
  label: {
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: "0.16em",
    textTransform: "uppercase" as const,
    color: "#3b82f6",
    marginBottom: 16,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  },
  heading: {
    fontSize: 44,
    fontWeight: 900,
    letterSpacing: "-0.035em",
    color: "#f1f5f9",
    margin: "0 0 16px 0",
    lineHeight: 1.08,
  },
  sub: {
    fontSize: 15,
    color: "#64748b",
    lineHeight: 1.65,
    margin: 0,
    maxWidth: 520,
  },
  cardRow: {
    display: "flex",
    gap: 20,
    overflowX: "auto",
    paddingBottom: 8,
    scrollbarWidth: "none" as const,
  },
  navRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginTop: 24,
  },
  dot: {
    height: 8,
    borderRadius: 100,
    border: "none",
    cursor: "pointer",
    padding: 0,
    transition: "width 0.2s, background 0.2s",
  },
  hint: {
    marginTop: 10,
    fontSize: 11,
    color: "#334155",
    letterSpacing: "0.03em",
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  },
};
