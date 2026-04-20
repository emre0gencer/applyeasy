import { useEffect, useState } from "react";
import { StatusResponse, getDownloadUrl } from "../api/client";
import { ChangeSummaryPanel } from "./ChangeSummaryPanel";
import { computeSuitabilityScore, scoreLabel } from "../utils/scoreUtils";

interface Props {
  runId: string;
  status: StatusResponse;
  onRestart: () => void;
  includeCoverLetter?: boolean;
}

// ── Suitability Score ──────────────────────────────────────────────────────

function SuitabilityScore({ status }: { status: StatusResponse }) {
  const score = computeSuitabilityScore(status);
  const label = scoreLabel(score);
  const kwCoverage = status.keyword_coverage ?? 0;
  const expDepth = Math.min((status.experience_count ?? 0) / 3, 1);
  const clarity = status.extraction_confidence ?? 0;
  const metrics = [
    { label: "Keyword alignment", value: kwCoverage },
    { label: "Experience depth", value: expDepth },
    { label: "Profile clarity", value: clarity },
  ];
  const [animated, setAnimated] = useState(false);
  const [countedScore, setCountedScore] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 80);
    return () => clearTimeout(t);
  }, []);

  // Count the number up from 0 once animation starts.
  // Step by 2 until within 5 of target, then step by 1 for a smooth finish.
  useEffect(() => {
    if (!animated) return;
    if (countedScore >= score) return;
    const remaining = score - countedScore;
    const step = remaining > 5 ? 2 : 1;
    const delay = remaining <= 5 ? 30 : 18;
    const t = setTimeout(() => setCountedScore((p) => Math.min(p + step, score)), delay);
    return () => clearTimeout(t);
  }, [animated, countedScore, score]);

  const r = 30;
  const circ = 2 * Math.PI * r;
  const targetOffset = circ * (1 - score / 100);
  const currentOffset = animated ? targetOffset : circ;

  return (
    <div style={sc.block}>
      <div style={sc.topRow}>
        <span style={sc.sectionLabel}>Match Score</span>
        <span style={sc.labelPill}>{label}</span>
      </div>

      <div style={sc.body}>
        {/* Arc ring — shows tailored score */}
        <div style={sc.circleWrap}>
          <svg width={80} height={80} style={{ display: "block", overflow: "visible" }}>
            <circle cx={40} cy={40} r={r} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={5} />
            <circle
              cx={40} cy={40} r={r}
              fill="none"
              stroke="#60a5fa"
              strokeWidth={5}
              strokeLinecap="round"
              strokeDasharray={`${circ}`}
              strokeDashoffset={`${currentOffset}`}
              transform="rotate(-90 40 40)"
              style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1)" }}
            />
          </svg>
          <div style={sc.circleText}>
            <span style={sc.scoreNum}>{countedScore}</span>
            <span style={sc.scoreOf}>/100</span>
          </div>
        </div>

        {/* Sub-metrics */}
        <div style={sc.metrics}>
          {metrics.map((m, i) => (
            <div key={i} style={sc.metricRow}>
              <div style={sc.metricHeader}>
                <span style={sc.metricLabel}>{m.label}</span>
                <span style={sc.metricPct}>{Math.round(m.value * 100)}%</span>
              </div>
              <div style={sc.barTrack}>
                <div
                  style={{
                    ...sc.barFill,
                    width: animated ? `${Math.round(m.value * 100)}%` : "0%",
                    transition: `width ${0.7 + i * 0.12}s cubic-bezier(0.4,0,0.2,1)`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Before / After comparison strip */}
      {status.raw_suitability_score !== undefined && status.raw_suitability_score !== null && (
        (() => {
          const rawInput = status.raw_suitability_score;
          return (
            <div style={sc.compareStrip}>
              <div style={sc.compareCol}>
                <span style={sc.compareCaption}>BEFORE TAILORING</span>
                <span style={sc.compareNumMuted}>{rawInput}</span>
              </div>
              <div style={sc.compareArrow}>→</div>
              <div style={sc.compareCol}>
                <span style={sc.compareCaption}>AFTER TAILORING</span>
                <span style={sc.compareNumBright}>{score}</span>
              </div>
              <div style={sc.compareDelta}>
                <span style={sc.compareDeltaNum}>
                  +{Math.max(0, score - rawInput)}
                </span>
                <span style={sc.compareDeltaLabel}>pts</span>
              </div>
            </div>
          );
        })()
      )}
    </div>
  );
}

const sc: Record<string, React.CSSProperties> = {
  block: {
    background: "rgba(255,255,255,0.04)",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    padding: "24px 40px 26px",
  },
  topRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 16,
  },
  sectionLabel: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "#64748b",
  },
  labelPill: {
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "#94a3b8",
    background: "rgba(255,255,255,0.08)",
    padding: "3px 8px",
    borderRadius: 4,
  },
  body: {
    display: "flex",
    alignItems: "center",
    gap: 28,
  },
  circleWrap: {
    position: "relative",
    width: 80,
    height: 80,
    flexShrink: 0,
  },
  circleText: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  },
  scoreNum: {
    fontSize: 22,
    fontWeight: 800,
    color: "#f1f5f9",
    lineHeight: 1,
    letterSpacing: "-0.03em",
  },
  scoreOf: {
    fontSize: 8,
    color: "#64748b",
    marginTop: 2,
    letterSpacing: "0.04em",
  },
  metrics: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 11,
  },
  metricRow: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  metricHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
  },
  metricLabel: {
    fontSize: 10,
    color: "#94a3b8",
    letterSpacing: "0.03em",
  },
  metricPct: {
    fontSize: 10,
    fontWeight: 700,
    color: "#e2e8f0",
    fontVariantNumeric: "tabular-nums" as React.CSSProperties["fontVariantNumeric"],
  },
  barTrack: {
    height: 3,
    background: "rgba(255,255,255,0.1)",
    borderRadius: 2,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    background: "#60a5fa",
    borderRadius: 2,
  },
  compareStrip: {
    display: "flex",
    alignItems: "center",
    gap: 0,
    marginTop: 16,
    paddingTop: 14,
    borderTop: "1px solid rgba(255,255,255,0.08)",
  },
  compareCol: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  compareCaption: {
    fontSize: 8,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    color: "#64748b",
  },
  compareNumMuted: {
    fontSize: 26,
    fontWeight: 800,
    color: "#475569",
    lineHeight: 1,
    letterSpacing: "-0.03em",
    fontVariantNumeric: "tabular-nums" as React.CSSProperties["fontVariantNumeric"],
  },
  compareNumBright: {
    fontSize: 26,
    fontWeight: 800,
    color: "#f1f5f9",
    lineHeight: 1,
    letterSpacing: "-0.03em",
    fontVariantNumeric: "tabular-nums" as React.CSSProperties["fontVariantNumeric"],
  },
  compareArrow: {
    fontSize: 14,
    color: "#475569",
    padding: "0 12px",
    flexShrink: 0,
    paddingBottom: 4,
    alignSelf: "flex-end",
  },
  compareDelta: {
    display: "flex",
    alignItems: "baseline",
    gap: 2,
    paddingLeft: 16,
    borderLeft: "1px solid rgba(255,255,255,0.08)",
    marginLeft: 4,
  },
  compareDeltaNum: {
    fontSize: 22,
    fontWeight: 800,
    color: "#16a34a",
    lineHeight: 1,
    letterSpacing: "-0.03em",
  },
  compareDeltaLabel: {
    fontSize: 10,
    fontWeight: 600,
    color: "#16a34a",
    letterSpacing: "0.04em",
  },
};

// ── Download card ──────────────────────────────────────────────────────────

function DownloadCard({
  icon,
  title,
  description,
  onClick,
  variant,
  locked = false,
}: {
  icon: string;
  title: string;
  description: string;
  onClick: () => void;
  variant: "primary" | "secondary";
  locked?: boolean;
}) {
  const [hovered, setHovered] = useState(false);

  if (locked) {
    return (
      <div style={{ ...s.dlCard, ...s.dlCardLocked, position: "relative" }}>
        <div style={s.proBadge}>PRO</div>
        <div style={{ ...s.dlCardBody, opacity: 0.45 }}>
          <span style={{ ...s.dlIcon, color: "#94a3b8" }}>{icon}</span>
          <div>
            <div style={{ ...s.dlTitle, color: "#94a3b8" }}>{title}</div>
            <div style={s.dlDesc}>{description}</div>
          </div>
        </div>
        <button
          style={{
            ...s.dlBtn,
            ...s.dlBtnLocked,
            ...(hovered ? s.dlBtnLockedHover : {}),
          }}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          <span style={s.lockIcon}>🔒</span>
          Unlock to download
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        ...s.dlCard,
        ...(variant === "secondary" ? s.dlCardSecondary : s.dlCardPrimary),
      }}
    >
      <div style={s.dlCardBody}>
        <span style={{ ...s.dlIcon, color: variant === "primary" ? "#e2e8f0" : "#64748b" }}>{icon}</span>
        <div>
          <div style={{ ...s.dlTitle, color: variant === "primary" ? "#e2e8f0" : "#64748b" }}>{title}</div>
          <div style={s.dlDesc}>{description}</div>
        </div>
      </div>
      <button
        style={{
          ...s.dlBtn,
          ...(variant === "secondary" ? s.dlBtnSecondary : s.dlBtnPrimary),
          ...(hovered ? (variant === "secondary" ? s.dlBtnSecondaryHover : s.dlBtnPrimaryHover) : {}),
        }}
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        Download ↓
      </button>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export function ResultsStep({ runId, status, onRestart }: Props) {
  const flags = (status.validation_flags ?? []).filter(
    (f) => !f.includes("rephrased")
  );
  const hasErrors = flags.some((f) => f.includes("warning") || f.includes("fabricat"));

  const rawInput = status.raw_suitability_score;
  const showOutOfScopeAlert = rawInput !== null && rawInput !== undefined && rawInput < 25;
  const showWeakAlert = !showOutOfScopeAlert &&
    rawInput !== null && rawInput !== undefined && rawInput < 50;

  function download(doc: "resume" | "cover-letter" | "summary") {
    window.open(getDownloadUrl(runId, doc), "_blank");
  }

  return (
    <div style={s.card}>

      {/* ── Out-of-scope alert (raw < 25) ── */}
      {showOutOfScopeAlert && (
        <div style={s.oosAlert}>
          <div style={s.weakAlertTop}>
            <span style={{ ...s.weakAlertIcon, color: "#f87171" }}>✕</span>
            <strong style={{ ...s.weakAlertTitle, color: "#fca5a5" }}>Profile appears out of scope for this role.</strong>
          </div>
          <p style={{ ...s.weakAlertBody, color: "#fca5a5" }}>
            {`Raw suitability score: ${rawInput}/100. `}
            Your experience and projects appear fundamentally mismatched with what this job requires.
            The generated resume has very limited keyword coverage and is unlikely to be competitive.
            <br /><br />
            <strong>This tool is not designed to bridge unrelated backgrounds.</strong> Consider applying to roles that genuinely match your experience, or significantly develop the required skills before resubmitting.
          </p>
        </div>
      )}

      {/* ── Weak profile alert (raw 25–49) ── */}
      {showWeakAlert && (
        <div style={s.weakAlert}>
          <div style={s.weakAlertTop}>
            <span style={s.weakAlertIcon}>⚠</span>
            <strong style={s.weakAlertTitle}>Low likelihood of acceptance at this role.</strong>
          </div>
          <p style={s.weakAlertBody}>
            Raw input data doesn't contain representation of certain needed qualifications
            {` — raw suitability score: ${rawInput}/100`}. The output PDF is suboptimal as a result.
            <br /><br />
            <strong>Sharpening your sword and coming back might be smart.</strong> Add more targeted experience, projects, or skills to your profile before resubmitting.
          </p>
        </div>
      )}

      {/* ── Header ── */}
      <div style={s.cardHeader}>
        <div style={s.successDot}>✓</div>
        <div>
          <h2 style={s.title}>Your documents are ready.</h2>
          <p style={s.subtitle}>Review carefully before submitting — all facts should reflect your actual experience.</p>
        </div>
      </div>

      <div style={s.divider} />

      {/* ── Match score panel ── */}
      <SuitabilityScore status={status} />

      {/* ── Downloads ── */}
      <div style={s.dlGrid}>
        <DownloadCard
          icon="📄"
          title="Resume"
          description="ATS-safe one-page PDF"
          onClick={() => download("resume")}
          variant="primary"
        />
        <DownloadCard
          icon="✉"
          title="Cover Letter"
          description="Grounded narrative, no filler"
          onClick={() => download("cover-letter")}
          variant="secondary"
          locked
        />
      </div>

      {/* ── Change viewer ── */}
      <ChangeSummaryPanel runId={runId} />

      <div style={s.divider} />

      {/* ── Validation flags ── */}
      {flags.length > 0 && (
        <div style={{ ...s.flagsBlock, borderColor: hasErrors ? "#fca5a5" : "#fde68a" }}>
          {flags.map((flag, i) => {
            const isError = flag.includes("warning") || flag.includes("fabricat");
            return (
              <div key={i} style={s.flagRow}>
                <span style={{ ...s.flagDot, background: isError ? "#dc2626" : "#d97706" }} />
                <span style={{ ...s.flagText, color: isError ? "#7f1d1d" : "#78350f" }}>{flag}</span>
              </div>
            );
          })}
        </div>
      )}

      {flags.length === 0 && (
        <div style={s.allClear}>
          <span style={s.allClearIcon}>✓</span>
          <span style={s.allClearText}>No validation issues detected</span>
        </div>
      )}

      {/* ── Footer ── */}
      <div style={s.footer}>
        <button style={s.restartBtn} onClick={onRestart}>
          ← Start a new application
        </button>
        <button style={s.summaryLink} onClick={() => download("summary")}>
          Raw JSON
        </button>
      </div>

    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 800,
    margin: "0 auto",
    background: "rgba(2,15,36,0.82)",
    backdropFilter: "blur(20px)",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,0.09)",
    boxShadow: "0 4px 6px -1px rgba(0,0,0,0.4), 0 24px 64px -12px rgba(0,0,0,0.55)",
    overflow: "hidden",
  },

  cardHeader: {
    display: "flex",
    alignItems: "flex-start",
    gap: 20,
    padding: "36px 40px 28px",
  },
  successDot: {
    width: 48,
    height: 48,
    borderRadius: "50%",
    background: "rgba(22,163,74,0.1)",
    border: "1px solid rgba(22,163,74,0.22)",
    color: "#16a34a",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 20,
    fontWeight: 700,
    flexShrink: 0,
    marginTop: 2,
  },
  title: {
    fontSize: 24,
    fontWeight: 700,
    color: "#f1f5f9",
    margin: "0 0 5px 0",
    letterSpacing: "-0.025em",
  },
  subtitle: {
    fontSize: 14,
    color: "#64748b",
    lineHeight: 1.5,
    margin: 0,
  },

  divider: {
    height: 1,
    background: "rgba(255,255,255,0.08)",
    margin: "0 40px",
  },

  dlGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 12,
    padding: "24px 40px",
  },
  dlCard: {
    borderRadius: 10,
    padding: "20px 20px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
    border: "1px solid",
  },
  dlCardPrimary: {
    background: "rgba(255,255,255,0.055)",
    borderColor: "rgba(255,255,255,0.12)",
  },
  dlCardSecondary: {
    background: "rgba(255,255,255,0.03)",
    borderColor: "rgba(255,255,255,0.08)",
  },
  dlCardBody: {
    display: "flex",
    gap: 12,
    alignItems: "flex-start",
  },
  dlIcon: {
    fontSize: 24,
    lineHeight: 1,
    marginTop: 1,
  },
  dlTitle: {
    fontSize: 15,
    fontWeight: 700,
    marginBottom: 3,
    color: "#e2e8f0",
  },
  dlDesc: {
    fontSize: 12,
    color: "#64748b",
    lineHeight: 1.4,
  },
  dlBtn: {
    width: "100%",
    padding: "13px 14px",
    borderRadius: 7,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    border: "none",
    transition: "background 0.12s, transform 0.1s",
    letterSpacing: "-0.01em",
  },
  dlBtnPrimary: { background: "#2563eb", color: "#fff" },
  dlBtnPrimaryHover: { background: "#1d4ed8", transform: "translateY(-1px)" },
  dlBtnSecondary: { background: "rgba(255,255,255,0.07)", color: "#94a3b8" },
  dlBtnSecondaryHover: { background: "rgba(255,255,255,0.11)" },
  dlCardLocked: {
    background: "rgba(255,255,255,0.02)",
    borderColor: "rgba(255,255,255,0.07)",
    borderStyle: "dashed",
  },
  dlBtnLocked: {
    background: "linear-gradient(135deg, #78350f 0%, #92400e 100%)",
    color: "#fef3c7",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    cursor: "pointer",
    boxShadow: "0 1px 3px rgba(120,53,15,0.25)",
  },
  dlBtnLockedHover: {
    background: "linear-gradient(135deg, #92400e 0%, #b45309 100%)",
    transform: "translateY(-1px)",
    boxShadow: "0 3px 8px rgba(120,53,15,0.3)",
  },
  proBadge: {
    position: "absolute",
    top: 12,
    right: 12,
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: "0.1em",
    color: "#92400e",
    background: "linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)",
    border: "1px solid #f59e0b",
    padding: "2px 6px",
    borderRadius: 4,
  },
  lockIcon: { fontSize: 11, lineHeight: 1 },

  flagsBlock: {
    margin: "16px 40px",
    padding: "12px 16px",
    borderRadius: 8,
    border: "1px solid",
    background: "rgba(120,53,15,0.2)",
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  flagRow: { display: "flex", alignItems: "flex-start", gap: 8 },
  flagDot: { width: 6, height: 6, borderRadius: "50%", flexShrink: 0, marginTop: 5 },
  flagText: { fontSize: 13, lineHeight: 1.5 },

  allClear: {
    margin: "16px 40px",
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 16px",
    borderRadius: 8,
    background: "rgba(22,163,74,0.06)",
    border: "1px solid rgba(22,163,74,0.18)",
  },
  allClearIcon: { color: "#16a34a", fontWeight: 700, fontSize: 14 },
  allClearText: { fontSize: 13, color: "#4ade80", fontWeight: 500 },

  oosAlert: {
    padding: "16px 40px",
    background: "rgba(30,10,10,0.9)",
    borderBottom: "1px solid rgba(127,29,29,0.6)",
  },
  weakAlert: {
    padding: "16px 40px",
    background: "rgba(239,68,68,0.07)",
    borderBottom: "1px solid rgba(239,68,68,0.18)",
  },
  weakAlertTop: { display: "flex", alignItems: "center", gap: 8, marginBottom: 8 },
  weakAlertIcon: { fontSize: 14, color: "#f87171" },
  weakAlertTitle: { fontSize: 13, color: "#fca5a5", fontWeight: 700 },
  weakAlertBody: { fontSize: 13, color: "#fca5a5", lineHeight: 1.6, margin: 0 },

  footer: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "20px 40px 28px",
  },
  restartBtn: {
    padding: "10px 20px",
    background: "transparent",
    color: "#94a3b8",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  },
  summaryLink: {
    padding: "9px 14px",
    background: "transparent",
    color: "#475569",
    border: "none",
    fontSize: 12,
    cursor: "pointer",
    textDecoration: "underline",
    textDecorationColor: "#334155",
  },
};
