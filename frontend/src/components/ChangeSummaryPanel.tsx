import { useState } from "react";
import { BulletChange, ChangeSummary, fetchChangeSummary } from "../api/client";

interface Props {
  runId: string;
}

function highlightKeywords(text: string, keywords: string[]): React.ReactNode {
  if (!keywords.length) return text;
  const unique = [...new Set(keywords.map((k) => k.trim()).filter(Boolean))];
  const escaped = unique.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, i) =>
    unique.some((k) => k.toLowerCase() === part.toLowerCase()) ? (
      <mark key={i} style={s.kwMark}>{part}</mark>
    ) : (
      part
    )
  );
}

function ChangeCard({ change, index }: { change: BulletChange; index: number }) {
  const [open, setOpen] = useState(false);
  const isChanged = change.change_reason === "keyword_integration";

  return (
    <div style={{ ...s.changeCard, borderLeftColor: isChanged ? "#6366f1" : "rgba(255,255,255,0.07)" }}>
      <button style={s.changeCardTrigger} onClick={() => setOpen((v) => !v)}>
        <div style={s.changeCardLeft}>
          <span style={{ ...s.changeIndex, background: isChanged ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.05)", color: isChanged ? "#818cf8" : "#475569" }}>
            {index + 1}
          </span>
          <span style={s.changePreview}>
            {change.original_text.slice(0, 72)}{change.original_text.length > 72 ? "…" : ""}
          </span>
        </div>
        <div style={s.changeCardRight}>
          {isChanged && (
            <div style={s.kwPillRow}>
              {change.keywords_added.slice(0, 3).map((k) => (
                <span key={k} style={s.kwPill}>{k}</span>
              ))}
              {change.keywords_added.length > 3 && (
                <span style={s.kwPillMore}>+{change.keywords_added.length - 3}</span>
              )}
            </div>
          )}
          <span style={{ ...s.chevron, transform: open ? "rotate(180deg)" : "none" }}>▾</span>
        </div>
      </button>

      {open && (
        <div style={s.diffBody}>
          <div style={s.diffBlock}>
            <div style={s.diffLabel}>
              <span style={s.diffLabelBefore}>ORIGINAL</span>
            </div>
            <p style={s.diffTextBefore}>{change.original_text}</p>
          </div>

          <div style={s.diffDivider}>
            <div style={s.diffDividerLine} />
            <span style={s.diffArrow}>↓ tailored</span>
            <div style={s.diffDividerLine} />
          </div>

          <div style={s.diffBlock}>
            <div style={s.diffLabel}>
              <span style={s.diffLabelAfter}>REWRITTEN</span>
              {change.keywords_added.length > 0 && (
                <span style={s.diffKwCount}>{change.keywords_added.length} keyword{change.keywords_added.length !== 1 ? "s" : ""} added</span>
              )}
            </div>
            <p style={s.diffTextAfter}>
              {highlightKeywords(change.revised_text, change.keywords_added)}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export function ChangeSummaryPanel({ runId }: Props) {
  const [state, setState] = useState<"idle" | "loading" | "loaded" | "error">("idle");
  const [summary, setSummary] = useState<ChangeSummary | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    if (state === "loaded") { setOpen((v) => !v); return; }
    setOpen(true);
    setState("loading");
    try {
      const data = await fetchChangeSummary(runId);
      setSummary(data);
      setState("loaded");
    } catch {
      setState("error");
    }
  }

  const allBullets = summary?.bullet_changes ?? [];
  const changed = allBullets.filter((c) => c.change_reason === "keyword_integration");
  const count = changed.length;

  return (
    <div style={s.root}>
      <button style={s.trigger} onClick={load}>
        <div style={s.triggerCheck}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8.5L6.5 12L13 5" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div style={s.triggerBody}>
          <span style={s.triggerTitle}>Resume tailored successfully</span>
          <span style={s.triggerSub}>
            {state === "loaded" && count > 0
              ? `${count} bullet${count !== 1 ? "s" : ""} rewritten with targeted keywords`
              : "View exactly what changed in your resume"}
          </span>
        </div>
        <div style={s.triggerRight}>
          {state === "loading" && <span style={s.triggerLoading}>loading…</span>}
          {state === "error" && <span style={s.triggerError}>failed</span>}
          <span style={s.triggerCaret}>{open && state === "loaded" ? "▾" : "▸"}</span>
        </div>
      </button>

      {open && state === "loaded" && summary && (
        <div style={s.panel}>
          <div style={s.panelHeader}>
            <span style={s.panelRole}>{summary.role_title} — {summary.company_name}</span>
            <span style={s.panelMeta}>
              {allBullets.length} processed
              <span style={s.panelMetaSep}>·</span>
              <span style={s.panelMetaGreen}>{count} addition{count !== 1 ? "s" : ""}</span>
            </span>
          </div>
          <div style={s.changeList}>
            {summary.bullet_changes.map((change, i) => (
              <ChangeCard key={i} change={change} index={i} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  root: {
    padding: "0 40px 24px",
  },

  /* Trigger button */
  trigger: {
    display: "flex",
    alignItems: "center",
    gap: 14,
    width: "100%",
    background: "rgba(5,46,22,0.55)",
    backdropFilter: "blur(12px)",
    border: "1.5px solid rgba(74,222,128,0.22)",
    borderRadius: 10,
    cursor: "pointer",
    padding: "13px 16px",
    textAlign: "left",
    fontFamily: "inherit",
    transition: "background 0.15s, border-color 0.15s",
    boxSizing: "border-box",
  },
  triggerCheck: {
    width: 34,
    height: 34,
    borderRadius: "50%",
    background: "rgba(20,83,45,0.7)",
    border: "2px solid rgba(74,222,128,0.3)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  triggerBody: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  triggerTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: "#f1f5f9",
    letterSpacing: "-0.01em",
  },
  triggerSub: {
    fontSize: 12,
    color: "#86efac",
    fontWeight: 400,
  },
  triggerRight: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  triggerCaret: {
    fontSize: 16,
    color: "#4ade80",
    lineHeight: 1,
  },
  triggerLoading: {
    fontSize: 12,
    color: "#94a3b8",
    fontWeight: 400,
  },
  triggerError: {
    fontSize: 12,
    color: "#f87171",
    fontWeight: 400,
  },

  /* Panel */
  panel: {
    marginTop: 8,
    border: "1px solid rgba(74,222,128,0.18)",
    borderRadius: 10,
    overflow: "hidden",
    background: "rgba(2,20,12,0.85)",
    backdropFilter: "blur(12px)",
  },
  panelHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "10px 16px",
    background: "rgba(5,46,22,0.7)",
    borderBottom: "1px solid rgba(74,222,128,0.12)",
  },
  panelRole: {
    fontSize: 13,
    fontWeight: 600,
    color: "#f1f5f9",
  },
  panelMeta: {
    fontSize: 12,
    color: "#64748b",
    display: "flex",
    alignItems: "center",
    gap: 5,
  },
  panelMetaSep: {
    color: "#334155",
  },
  panelMetaGreen: {
    color: "#4ade80",
    fontWeight: 600,
  },
  changeList: {
    display: "flex",
    flexDirection: "column",
  },

  /* Change card */
  changeCard: {
    borderLeft: "3px solid",
    borderBottom: "1px solid rgba(74,222,128,0.07)",
  },
  changeCardTrigger: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "11px 16px",
    background: "transparent",
    border: "none",
    cursor: "pointer",
    textAlign: "left",
  },
  changeCardLeft: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flex: 1,
    minWidth: 0,
  },
  changeIndex: {
    width: 22,
    height: 22,
    borderRadius: 5,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    flexShrink: 0,
  },
  changePreview: {
    fontSize: 13,
    color: "#94a3b8",
    lineHeight: 1.4,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  changeCardRight: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  kwPillRow: {
    display: "flex",
    gap: 4,
    flexWrap: "wrap",
  },
  kwPill: {
    fontSize: 11,
    fontWeight: 500,
    color: "#818cf8",
    background: "rgba(99,102,241,0.15)",
    padding: "2px 7px",
    borderRadius: 100,
    whiteSpace: "nowrap",
  },
  kwPillMore: {
    fontSize: 11,
    color: "#64748b",
    padding: "2px 4px",
  },
  chevron: {
    fontSize: 16,
    color: "#64748b",
    transition: "transform 0.15s",
    lineHeight: 1,
  },

  /* Diff body */
  diffBody: {
    padding: "0 16px 16px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  diffBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  diffLabel: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginBottom: 2,
  },
  diffLabelBefore: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.08em",
    color: "#64748b",
  },
  diffLabelAfter: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.08em",
    color: "#4ade80",
  },
  diffKwCount: {
    fontSize: 11,
    color: "#64748b",
  },
  diffTextBefore: {
    fontSize: 13,
    color: "#64748b",
    lineHeight: 1.6,
    background: "rgba(255,255,255,0.04)",
    padding: "10px 12px",
    borderRadius: 6,
    border: "1px solid rgba(255,255,255,0.07)",
    margin: 0,
    fontStyle: "italic",
  },
  diffTextAfter: {
    fontSize: 13,
    color: "#f1f5f9",
    lineHeight: 1.6,
    background: "rgba(5,46,22,0.45)",
    padding: "10px 12px",
    borderRadius: 6,
    border: "1px solid rgba(74,222,128,0.2)",
    margin: 0,
  },
  diffDivider: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 0",
  },
  diffDividerLine: {
    flex: 1,
    height: 1,
    background: "rgba(255,255,255,0.06)",
  },
  diffArrow: {
    fontSize: 11,
    color: "#475569",
    letterSpacing: "0.03em",
    whiteSpace: "nowrap",
  },

  /* Keyword highlight */
  kwMark: {
    background: "rgba(74,222,128,0.15)",
    color: "#86efac",
    padding: "0 2px",
    borderRadius: 3,
    fontWeight: 600,
    fontStyle: "normal",
  },
};
