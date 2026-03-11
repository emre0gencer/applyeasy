import { useEffect, useState } from "react";
import { getStatus, StatusResponse } from "../api/client";

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

function computeFinalScore(status: StatusResponse): number {
  const kwCoverage = status.keyword_coverage ?? 0;
  const expDepth = Math.min((status.experience_count ?? 0) / 3, 1);
  const clarity = status.extraction_confidence ?? 0;
  const raw = kwCoverage * 50 + expDepth * 25 + clarity * 25;
  const severe = (status.validation_flags ?? []).filter((f) =>
    f.toLowerCase().includes("truthfulness") || f.toLowerCase().includes("fabricat")
  ).length;
  return Math.max(0, Math.min(100, Math.round(raw - severe * 10)));
}

function scoreLabel(score: number): string {
  if (score >= 85) return "Excellent fit";
  if (score >= 70) return "Strong match";
  if (score >= 55) return "Good match";
  if (score >= 40) return "Moderate fit";
  return "Weak match";
}

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
  const [pauseDone, setPauseDone] = useState(false);

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

  // Tailored score: available after tailoring_resume
  const tailoringDone = status != null && (status.keyword_coverage != null || isCompleted);
  const finalScore = tailoringDone ? computeFinalScore(status!) : null;

  // Display caps:
  //   max +35 pts improvement over raw
  //   if raw < 55: final display ≤ 70
  const cappedFinalScore = finalScore !== null && rawScore !== null
    ? Math.min(finalScore, rawScore + 35, rawScore < 55 ? 70 : 100)
    : finalScore;

  // Enforce minimum +20 gap: clamp displayed raw downward based on capped final
  const effectiveRaw = rawScore !== null
    ? (cappedFinalScore !== null ? Math.min(rawScore, Math.max(0, cappedFinalScore - 20)) : rawScore)
    : null;

  // ── Animation effects ──────────────────────────────────────────────────────

  // Start phase1 as soon as scoring_relevance step begins (before rawScore arrives)
  useEffect(() => {
    if (scoringStarted && animPhase === "idle") setAnimPhase("phase1");
  }, [scoringStarted, animPhase]);

  // Phase 1: counts up from 0 toward effectiveRaw (or 90 placeholder).
  // When it reaches the target, snaps displayedRaw to exactly effectiveRaw
  // before entering pause — guarantees no overshoot mismatch vs ResultsStep.
  useEffect(() => {
    if (animPhase !== "phase1") return;
    const target = effectiveRaw !== null ? effectiveRaw : 90;
    if (displayedRaw >= target) {
      if (effectiveRaw !== null) {
        setDisplayedRaw(effectiveRaw); // snap to exact final value
        setAnimPhase("pause");
      }
      // else: hold at 90 until rawScore arrives
      return;
    }
    const t = setTimeout(() => setDisplayedRaw((p) => p + 1), 55);
    return () => clearTimeout(t);
  }, [animPhase, displayedRaw, effectiveRaw]);

  // 1-second pause between phases
  useEffect(() => {
    if (animPhase !== "pause") return;
    const t = setTimeout(() => setPauseDone(true), 1000);
    return () => clearTimeout(t);
  }, [animPhase]);

  // Transition pause → phase2 immediately once pause timer fires (don't wait for cappedFinalScore).
  // Phase 2 starts from displayedRaw (the settled phase 1 value = effectiveRaw).
  useEffect(() => {
    if (!pauseDone || animPhase !== "pause" || effectiveRaw === null) return;
    setDisplayedTailored(displayedRaw); // start from where phase 1 landed
    setAnimPhase("phase2");
  }, [pauseDone, animPhase, effectiveRaw, displayedRaw]);

  // Phase 2: counts toward cappedFinalScore (or a placeholder if not yet available).
  // Holds at placeholder until real value arrives, then continues to real target.
  useEffect(() => {
    if (animPhase !== "phase2") return;
    // Use real target if available, otherwise count toward a placeholder so the bar visibly moves
    const target = cappedFinalScore ?? (effectiveRaw !== null ? Math.min(effectiveRaw + 20, 95) : 95);
    if (displayedTailored >= target) {
      if (cappedFinalScore !== null) {
        setDisplayedTailored(cappedFinalScore); // snap to exact final
        setAnimPhase("done");
      }
      // else: hold at placeholder until cappedFinalScore arrives
      return;
    }
    const t = setTimeout(
      () => setDisplayedTailored((p) => Math.min(p + 1, target)),
      Math.round(55 * 0.75)   // 41ms per tick
    );
    return () => clearTimeout(t);
  }, [animPhase, displayedTailored, cappedFinalScore, effectiveRaw]);

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
          <svg width="52" height="52" viewBox="0 0 52 52">
            <circle cx="26" cy="26" r="22" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="4" />
            <circle
              cx="26" cy="26" r="22"
              fill="none"
              stroke={isCompleted ? "#16a34a" : "#6366f1"}
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 22}`}
              strokeDashoffset={`${2 * Math.PI * 22 * (1 - doneCount / STEPS.length)}`}
              style={{ transform: "rotate(-90deg)", transformOrigin: "26px 26px", transition: "stroke-dashoffset 0.5s ease" }}
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
            {animPhase === "done" && cappedFinalScore !== null && effectiveRaw !== null && (
              <span style={sg.deltaBadge}>
                +{Math.max(0, cappedFinalScore - effectiveRaw)} pts improvement
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
              <span style={{ ...sg.halfLabel, color: animPhase === "done" ? "#16a34a" : "#555" }}>
                {animPhase === "done" && cappedFinalScore !== null
                  ? scoreLabel(cappedFinalScore)
                  : animPhase === "phase2" ? "tailoring…"
                  : animPhase === "pause" ? "tailoring…"
                  : "calculating…"}
              </span>
            </div>

          </div>
        </div>
      )}

      {/* ── Step list ── */}
      <div style={s.stepList}>
        {STEPS.map((step, i) => {
          const isDone = isCompleted || currentIndex > i;
          const isActive = !isCompleted && currentIndex === i && status?.status === "running";
          const state: DotState = isDone ? "done" : isActive ? "active" : "pending";
          const isLast = i === STEPS.length - 1;

          return (
            <div key={step.key} style={s.stepRow}>
              <div style={s.dotCol}>
                <StepDot state={state} />
                {!isLast && (
                  <div style={{ ...s.connector, background: isDone ? "#16a34a" : "rgba(255,255,255,0.12)" }} />
                )}
              </div>
              <div style={{ ...s.stepText, paddingBottom: isLast ? 0 : 20 }}>
                <span style={{
                  ...s.stepLabel,
                  color: isDone ? "#e2e8f0" : isActive ? "#f1f5f9" : "#475569",
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
                  <span style={{ ...s.stepDetail, color: "#cbd5e1" }}>{step.detail}</span>
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

// ── Score strip styles (dark panel) ─────────────────────────────────────────

const sg: Record<string, React.CSSProperties> = {
  strip: {
    background: "#e8e8e8",
    borderRadius: 6,
    border: "1.5px solid #111",
    padding: "12px 12px 10px",
    marginBottom: 24,
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  headerLabel: {
    fontSize: 8,
    fontWeight: 700,
    letterSpacing: "0.14em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#444",
  },
  deltaBadge: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.06em",
    color: "#fff",
    background: "#111",
    border: "1px solid #111",
    padding: "2px 7px",
    borderRadius: 3,
  },
  // Split two-column layout
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
    background: "#fff",
    border: "1px solid #111",
    borderRadius: 4,
    padding: "10px 14px 8px",
  },
  centerDivider: {
    display: "none",
  },
  halfBarTrack: {
    height: 4,
    background: "#ddd",
    borderRadius: 1,
    overflow: "hidden",
    position: "relative",
    border: "1px solid #ccc",
  },
  barWhite: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    background: "#333",
    borderRadius: 1,
  },
  barGreen: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    background: "#111",
    borderRadius: 1,
  },
  halfLabel: {
    fontSize: 8,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#555",
    marginTop: 1,
  },
  numCaption: {
    fontSize: 8,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase" as React.CSSProperties["textTransform"],
    color: "#555",
  },
  numLine: {
    display: "flex",
    alignItems: "baseline",
    gap: 2,
  },
  numWhite: {
    fontSize: 36,
    fontWeight: 800,
    color: "#111",
    lineHeight: 1,
    letterSpacing: "-0.04em",
    fontVariantNumeric: "tabular-nums" as React.CSSProperties["fontVariantNumeric"],
    minWidth: 44,
  },
  numGreen: {
    fontSize: 36,
    fontWeight: 800,
    color: "#111",
    lineHeight: 1,
    letterSpacing: "-0.04em",
    fontVariantNumeric: "tabular-nums" as React.CSSProperties["fontVariantNumeric"],
    minWidth: 44,
  },
  numDash: {
    fontSize: 36,
    fontWeight: 800,
    color: "#ccc",
    lineHeight: 1,
    letterSpacing: "-0.04em",
    minWidth: 44,
  },
  numOf: {
    fontSize: 9,
    color: "#666",
    letterSpacing: "0.03em",
  },
};

// ── Main card styles ─────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 520,
    margin: "0 auto",
    background: "rgba(2,15,36,0.8)",
    backdropFilter: "blur(16px)",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.1)",
    boxShadow: "0 4px 6px -1px rgba(0,0,0,0.4), 0 20px 60px -10px rgba(0,0,0,0.5)",
    padding: "28px 32px 24px",
  },
  cardTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 28,
  },
  headerText: { flex: 1 },
  title: {
    fontSize: 20,
    fontWeight: 700,
    color: "#f1f5f9",
    margin: "0 0 4px 0",
    letterSpacing: "-0.02em",
  },
  subtitle: { fontSize: 13, color: "#94a3b8", margin: 0 },
  progressCircle: { position: "relative", width: 52, height: 52, flexShrink: 0 },
  progressLabel: {
    position: "absolute",
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%)",
    fontSize: 11,
    fontWeight: 700,
    lineHeight: 1,
  },
  stepList: { display: "flex", flexDirection: "column" },
  stepRow: { display: "flex", alignItems: "flex-start", gap: 14 },
  dotCol: { display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 },
  connector: { width: 2, flex: 1, minHeight: 16, borderRadius: 1, marginTop: 2 },
  stepText: { display: "flex", flexDirection: "column", gap: 2, paddingTop: 4 },
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
