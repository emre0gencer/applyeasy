import { useEffect, useState } from "react";
import { getStatus, StatusResponse } from "../api/client";
import { computeSuitabilityScore, scoreLabel } from "../utils/scoreUtils";

interface Props {
  runId: string;
  onDone: (status: StatusResponse) => void;
  onFailed: (msg: string) => void;
  includeCoverLetter?: boolean;
}

const BASE_STEPS = [
  { key: "extracting_profile",      label: "Extracting your profile",        detail: "Parsing work history, projects, skills" },
  { key: "analyzing_job",           label: "Analyzing job description",       detail: "Identifying required keywords and skills" },
  { key: "scoring_relevance",       label: "Scoring relevance",               detail: "Matching your experience to the role" },
  { key: "tailoring_resume",        label: "Tailoring resume",                detail: "Rewriting bullets with targeted keywords" },
  { key: "generating_cover_letter", label: "Drafting cover letter",           detail: "Building grounded narrative from evidence" },
  { key: "rendering_pdfs",          label: "Rendering PDFs",                  detail: "Generating ATS-safe documents" },
];

function stepIndex(steps: typeof BASE_STEPS, key: string): number {
  return steps.findIndex((s) => s.key === key);
}

type DotState = "done" | "active" | "pending";

function StepDot({ state }: { state: DotState }) {
  return (
    <div style={{ ...dot.base, ...dot[state] }}>
      {state === "done" ? (
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M1.5 5L4 7.5L8.5 2.5" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : state === "active" ? (
        <div style={dot.innerPulse} />
      ) : (
        <div style={dot.innerEmpty} />
      )}
    </div>
  );
}

const dot: Record<string, React.CSSProperties> = {
  base: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    zIndex: 1,
    position: "relative",
  },
  done:    { background: "#16a34a", boxShadow: "0 0 0 3px rgba(22,163,74,0.15)" },
  active:  { background: "rgba(2,15,36,0.8)", border: "2px solid #6366f1", boxShadow: "0 0 0 4px rgba(99,102,241,0.2)" },
  pending: { background: "rgba(255,255,255,0.05)", border: "2px solid rgba(255,255,255,0.15)" },
  innerPulse: { width: 8, height: 8, borderRadius: "50%", background: "#6366f1" },
  innerEmpty: { width: 6, height: 6, borderRadius: "50%", background: "#cbd5e1" },
};

// ── Score helpers ────────────────────────────────────────────────────────────
// computeSuitabilityScore and scoreLabel are imported from ../utils/scoreUtils
// so both GeneratingStep and ResultsStep use the exact same formula.

// ── Main component ───────────────────────────────────────────────────────────

export function GeneratingStep({ runId, onDone, onFailed, includeCoverLetter = false }: Props) {
  const STEPS = includeCoverLetter
    ? BASE_STEPS
    : BASE_STEPS.filter((s) => s.key !== "generating_cover_letter");

  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [completedStatus, setCompletedStatus] = useState<StatusResponse | null>(null);

  // Two-phase animation state machine
  // phase1: gray bar grows 0→effectiveRaw (5s)
  // pause:  2s freeze
  // phase2: green bar grows effectiveRaw→finalScore (5s)
  // done:   both fixed, transition to results
  type AnimPhase = "idle" | "phase1" | "pause" | "phase2" | "done";
  const [animPhase, setAnimPhase] = useState<AnimPhase>("idle");
  const [displayedRaw, setDisplayedRaw] = useState(0);
  const [displayedTailored, setDisplayedTailored] = useState(0);

  // Poll pipeline status
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      while (!cancelled) {
        try {
          const s = await getStatus(runId);
          if (!cancelled) setStatus(s);
          if (s.status === "completed") { if (!cancelled) setCompletedStatus(s); return; }
          if (s.status === "failed")    { if (!cancelled) onFailed(s.error_message ?? "Generation failed"); return; }
        } catch { /* keep polling */ }
        await new Promise((r) => setTimeout(r, 2000));
      }
    }

    poll();
    return () => { cancelled = true; };
  }, [runId, onFailed]);

  const currentIndex = status ? stepIndex(STEPS, status.progress_step) : -1;
  const isCompleted = status?.status === "completed";
  const doneCount = isCompleted ? STEPS.length : Math.max(0, currentIndex);

  // Raw score: available after scoring_relevance completes
  const rawScore = status?.raw_suitability_score ?? null;
  const rawAvailable = rawScore !== null;

  // Strip appears when scoring_relevance step becomes active
  const scoringStarted =
    rawAvailable ||
    (status?.status === "running" && status?.progress_step === "scoring_relevance");

  // cappedFinalScore: computed ONLY from completedStatus so the animated final
  // value is guaranteed to match what ResultsStep displays. Never use the
  // intermediate tailoring_resume status — its keyword_coverage excludes the
  // skills section while the validator's (used at completion) includes it,
  // causing a different score from the same formula.
  const cappedFinalScore = completedStatus
    ? computeSuitabilityScore(completedStatus)
    : null;

  // effectiveRaw: raw bar target — always the true raw score, no clamping.
  const effectiveRaw = rawScore;

  // ── Animation effects ──────────────────────────────────────────────────────

  // Start phase1 only once rawScore is actually known — never count toward a placeholder.
  useEffect(() => {
    if (rawAvailable && animPhase === "idle") setAnimPhase("phase1");
  }, [rawAvailable, animPhase]);

  // Phase 1: counts up from 0 toward effectiveRaw (always known when phase1 starts).
  useEffect(() => {
    if (animPhase !== "phase1" || effectiveRaw === null) return;
    if (displayedRaw >= effectiveRaw) {
      setDisplayedRaw(effectiveRaw);
      setAnimPhase("pause");
      return;
    }
    const t = setTimeout(() => setDisplayedRaw((p) => p + 1), 55);
    return () => clearTimeout(t);
  }, [animPhase, displayedRaw, effectiveRaw]);

  // After a brief pause, advance to phase2 as soon as cappedFinalScore is known.
  // Both animPhase and cappedFinalScore are deps so this re-fires when either changes.
  useEffect(() => {
    if (animPhase !== "pause" || cappedFinalScore === null) return;
    const t = setTimeout(() => {
      setDisplayedTailored(0);
      setAnimPhase("phase2");
    }, 300);
    return () => clearTimeout(t);
  }, [animPhase, cappedFinalScore]);

  // Phase 2: counts from displayedRaw toward cappedFinalScore (always known here).
  useEffect(() => {
    if (animPhase !== "phase2" || cappedFinalScore === null) return;
    if (displayedTailored >= cappedFinalScore) {
      setDisplayedTailored(cappedFinalScore); // snap to exact final
      setAnimPhase("done");
      return;
    }
    const t = setTimeout(
      () => setDisplayedTailored((p) => Math.min(p + 1, cappedFinalScore)),
      41  // ~41ms per tick
    );
    return () => clearTimeout(t);
  }, [animPhase, displayedTailored, cappedFinalScore]);

  // Fire onDone: immediately if no strip was ever shown, or after animation completes
  useEffect(() => {
    if (!completedStatus) return;
    if (!scoringStarted) { onDone(completedStatus); return; }
    if (animPhase === "done") { onDone(completedStatus); }
  }, [animPhase, completedStatus, scoringStarted, onDone]);

  return (
    <div style={s.card}>

      {/* ── Header ── */}
      <div style={s.cardTop}>
        <div style={s.headerText}>
          <h2 style={s.title}>
            {isCompleted ? "Done." : "Tailoring your resume…"}
          </h2>
          <p style={s.subtitle}>
            {isCompleted
              ? "All documents are ready to download."
              : "This typically takes 20–40 seconds."}
          </p>
        </div>
        <div style={s.progressCircle}>
          <svg width="64" height="64" viewBox="0 0 64 64">
            <circle cx="32" cy="32" r="27" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="4" />
            <circle
              cx="32" cy="32" r="27"
              fill="none"
              stroke={isCompleted ? "#16a34a" : "#6366f1"}
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 27}`}
              strokeDashoffset={`${2 * Math.PI * 27 * (1 - doneCount / STEPS.length)}`}
              style={{ transform: "rotate(-90deg)", transformOrigin: "32px 32px", transition: "stroke-dashoffset 0.5s ease" }}
            />
          </svg>
          <span style={{ ...s.progressLabel, color: isCompleted ? "#16a34a" : "#6366f1" }}>
            {doneCount}/{STEPS.length}
          </span>
        </div>
      </div>

      {/* ── Before / After score strip — split layout ── */}
      {scoringStarted && (
        <div style={sg.strip}>
          {/* Header */}
          <div style={sg.header}>
            <span style={sg.headerLabel}>SUITABILITY SCORE</span>
            {animPhase === "done" && cappedFinalScore !== null && rawScore !== null && rawScore > 0 && (
              <span style={sg.deltaBadge}>
                +{Math.max(0, cappedFinalScore - rawScore)} pts improvement
              </span>
            )}
          </div>

          {/* Two disconnected halves */}
          <div style={sg.splitRow}>

            {/* ── Left: Raw ── */}
            <div style={sg.halfBlock}>
              <span style={sg.numCaption}>RAW INPUT</span>
              <div style={sg.numLine}>
                <span style={sg.numWhite}>{displayedRaw}</span>
                <span style={sg.numOf}>/100</span>
              </div>
              <div style={sg.halfBarTrack}>
                <div style={{ ...sg.barWhite, width: `${displayedRaw}%` }} />
              </div>
              <span style={sg.halfLabel}>before</span>
            </div>

            {/* ── Center divider ── */}
            <div style={sg.centerDivider} />

            {/* ── Right: Tailored ── */}
            <div style={sg.halfBlock}>
              <span style={sg.numCaption}>TAILORED</span>
              <div style={sg.numLine}>
                {(animPhase === "phase2" || animPhase === "done") ? (
                  <>
                    <span style={sg.numGreen}>{displayedTailored}</span>
                    <span style={sg.numOf}>/100</span>
                  </>
                ) : (
                  <span style={sg.numDash}>—</span>
                )}
              </div>
              <div style={sg.halfBarTrack}>
                {(animPhase === "phase2" || animPhase === "done") && (
                  <div style={{ ...sg.barGreen, width: `${displayedTailored}%` }} />
                )}
              </div>
              <span style={{ ...sg.halfLabel, color: animPhase === "done" ? "#4ade80" : "#64748b" }}>
                {animPhase === "done" && cappedFinalScore !== null
                  ? scoreLabel(cappedFinalScore)
                  : (animPhase === "phase2" || animPhase === "pause") ? "loading…"
                  : "calculating…"}
              </span>
            </div>

          </div>
        </div>
      )}

      {/* ── Step list ── */}
      <div style={s.stepList}>
        {STEPS.map((step, i) => {
          const scoringIdx = stepIndex(STEPS, "scoring_relevance");
          // Keep scoring_relevance active (not green) while the score bars are still animating.
          // scoring_relevance stays active during phase1; turns green once raw bar finishes
          const rawBarActive = animPhase === "phase1";
          const pipelineDone = isCompleted || currentIndex > i;
          const isDone = (i === scoringIdx && rawBarActive) ? false : pipelineDone;
          const isActive = isDone ? false
            : (i === scoringIdx && rawBarActive)
              ? true
              : (!isCompleted && currentIndex === i && status?.status === "running");
          const state: DotState = isDone ? "done" : isActive ? "active" : "pending";
          const isLast = i === STEPS.length - 1;

          // connector between this step and the next: green if BOTH this and next are done
          const nextIsDone = i < STEPS.length - 1 && (() => {
            const ni = i + 1;
            const nPipelineDone = isCompleted || currentIndex > ni;
            return (ni === scoringIdx && rawBarActive) ? false : nPipelineDone;
          })();
          const connectorColor = isDone && nextIsDone
            ? "#16a34a"
            : isDone
            ? "rgba(22,163,74,0.35)"
            : "rgba(255,255,255,0.1)";

          return (
            <div key={step.key} style={s.stepRow}>
              <div style={s.dotCol}>
                <StepDot state={state} />
                {!isLast && (
                  <div style={{
                    ...s.connector,
                    background: connectorColor,
                    transition: "background 0.4s ease",
                  }} />
                )}
              </div>
              <div style={{ ...s.stepText, paddingBottom: isLast ? 0 : 24 }}>
                <span style={{
                  ...s.stepLabel,
                  color: isDone ? "#e2e8f0" : isActive ? "#f1f5f9" : "#3d4f63",
                  fontWeight: isActive ? 600 : isDone ? 500 : 400,
                }}>
                  {step.label}
                  {isActive && <span style={s.activeDot}>●</span>}
                </span>
                {(isActive || isDone) && (
                  <span style={{ ...s.stepDetail, color: isDone ? "#94a3b8" : "#6366f1" }}>
                    {isDone ? "complete" : step.detail}
                  </span>
                )}
                {!isActive && !isDone && (
                  <span style={{ ...s.stepDetail, color: "#3d4f63" }}>{step.detail}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Low confidence warning ── */}
      {status?.extraction_confidence !== undefined && status.extraction_confidence < 0.5 && (
        <div style={s.warn}>
          <span style={s.warnIcon}>⚠</span>
          <span>Low extraction confidence ({Math.round(status.extraction_confidence * 100)}%) — results may be less accurate. Try pasting text directly next time.</span>
        </div>
      )}

    </div>
  );
}

// ── Score strip styles ────────────────────────────────────────────────────────

const sg: Record<string, React.CSSProperties> = {
  strip: {
    background: "rgba(255,255,255,0.04)",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.1)",
    padding: "14px 14px 12px",
    marginBottom: 24,
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  headerLabel: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.14em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#475569",
  },
  deltaBadge: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.06em",
    color: "#4ade80",
    background: "rgba(22,163,74,0.15)",
    border: "1px solid rgba(22,163,74,0.3)",
    padding: "2px 8px",
    borderRadius: 3,
  },
  splitRow: {
    display: "flex",
    alignItems: "stretch",
    gap: 8,
  },
  halfBlock: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 5,
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.07)",
    borderRadius: 6,
    padding: "12px 16px 10px",
  },
  centerDivider: {
    display: "none",
  },
  halfBarTrack: {
    height: 4,
    background: "rgba(255,255,255,0.08)",
    borderRadius: 2,
    overflow: "hidden",
    position: "relative",
  },
  barWhite: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    background: "rgba(148,163,184,0.55)",
    borderRadius: 2,
  },
  barGreen: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    background: "#4ade80",
    borderRadius: 2,
  },
  halfLabel: {
    fontSize: 9,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#64748b",
    marginTop: 1,
  },
  numCaption: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#475569",
  },
  numLine: {
    display: "flex",
    alignItems: "baseline",
    gap: 2,
  },
  numWhite: {
    fontSize: 36,
    fontWeight: 800,
    color: "#94a3b8",
    lineHeight: 1,
    letterSpacing: "-0.04em",
    fontVariantNumeric: "tabular-nums" as React.CSSProperties["fontVariantNumeric"],
    minWidth: 44,
  },
  numGreen: {
    fontSize: 36,
    fontWeight: 800,
    color: "#4ade80",
    lineHeight: 1,
    letterSpacing: "-0.04em",
    fontVariantNumeric: "tabular-nums" as React.CSSProperties["fontVariantNumeric"],
    minWidth: 44,
  },
  numDash: {
    fontSize: 36,
    fontWeight: 800,
    color: "#334155",
    lineHeight: 1,
    letterSpacing: "-0.04em",
    minWidth: 44,
  },
  numOf: {
    fontSize: 9,
    color: "#475569",
    letterSpacing: "0.03em",
  },
};

// ── Main card styles ──────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 660,
    margin: "0 auto",
    background: "rgba(2,15,36,0.82)",
    backdropFilter: "blur(20px)",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,0.09)",
    boxShadow: "0 4px 6px -1px rgba(0,0,0,0.4), 0 24px 64px -12px rgba(0,0,0,0.55)",
    padding: "32px 40px 28px",
  },
  cardTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 32,
  },
  headerText: { flex: 1 },
  title: {
    fontSize: 24,
    fontWeight: 700,
    color: "#f1f5f9",
    margin: "0 0 5px 0",
    letterSpacing: "-0.025em",
  },
  subtitle: { fontSize: 14, color: "#64748b", margin: 0 },
  progressCircle: { position: "relative", width: 64, height: 64, flexShrink: 0 },
  progressLabel: {
    position: "absolute",
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%)",
    fontSize: 12,
    fontWeight: 700,
    lineHeight: 1,
  },
  stepList: { display: "flex", flexDirection: "column" },
  stepRow: { display: "flex", alignItems: "stretch", gap: 14 },
  dotCol: { display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: 28 },
  connector: { width: 2, flex: 1, minHeight: 12, borderRadius: 1, marginTop: -1, marginBottom: -1 },
  stepText: { display: "flex", flexDirection: "column", gap: 2, paddingTop: 6, flex: 1 },
  stepLabel: { fontSize: 14, lineHeight: 1.4, display: "flex", alignItems: "center", gap: 6 },
  activeDot: { fontSize: 8, color: "#6366f1" },
  stepDetail: { fontSize: 12, lineHeight: 1.4 },
  warn: {
    marginTop: 20,
    display: "flex",
    gap: 8,
    alignItems: "flex-start",
    padding: "10px 14px",
    background: "rgba(120,53,15,0.25)",
    border: "1px solid rgba(253,230,138,0.3)",
    borderRadius: 8,
    fontSize: 13,
    color: "#fde68a",
    lineHeight: 1.5,
  },
  warnIcon: { flexShrink: 0, marginTop: 1 },
};
