import { useEffect, useState } from "react";
import { getStatus, StatusResponse } from "../api/client";

interface Props {
  runId: string;
  onDone: (status: StatusResponse) => void;
  onFailed: (msg: string) => void;
}

const STEPS = [
  { key: "extracting_profile",      label: "Extracting your profile" },
  { key: "analyzing_job",           label: "Analyzing job description" },
  { key: "scoring_relevance",       label: "Scoring experience relevance" },
  { key: "tailoring_resume",        label: "Tailoring resume" },
  { key: "generating_cover_letter", label: "Drafting cover letter" },
  { key: "rendering_pdfs",          label: "Rendering PDFs" },
];

function stepIndex(key: string): number {
  return STEPS.findIndex((s) => s.key === key);
}

export function GeneratingStep({ runId, onDone, onFailed }: Props) {
  const [status, setStatus] = useState<StatusResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      while (!cancelled) {
        try {
          const s = await getStatus(runId);
          if (!cancelled) setStatus(s);
          if (s.status === "completed") {
            if (!cancelled) onDone(s);
            return;
          }
          if (s.status === "failed") {
            if (!cancelled) onFailed(s.error_message ?? "Generation failed");
            return;
          }
        } catch {
          // Network hiccup — keep polling
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    }

    poll();
    return () => { cancelled = true; };
  }, [runId, onDone, onFailed]);

  const currentIndex = status ? stepIndex(status.progress_step) : -1;

  return (
    <div style={styles.card}>
      <h2 style={styles.title}>Step 3 of 4: Generating...</h2>
      <p style={styles.subtitle}>This typically takes 20–40 seconds.</p>

      <div style={styles.stepList}>
        {STEPS.map((step, i) => {
          const isDone = currentIndex > i || status?.status === "completed";
          const isActive = currentIndex === i && status?.status === "running";
          const isPending = currentIndex < i && status?.status !== "completed";
          return (
            <div key={step.key} style={styles.stepRow}>
              <span style={{ ...styles.dot, ...(isDone ? styles.dotDone : isActive ? styles.dotActive : styles.dotPending) }}>
                {isDone ? "✓" : isActive ? "●" : "○"}
              </span>
              <span style={{ ...styles.stepLabel, ...(isDone ? styles.labelDone : isActive ? styles.labelActive : {}) }}>
                {step.label}
              </span>
              <span style={styles.stepStatus}>
                {isDone ? "done" : isActive ? "in progress" : isPending ? "waiting" : ""}
              </span>
            </div>
          );
        })}
      </div>

      {status?.extraction_confidence !== undefined && status.extraction_confidence < 0.5 && (
        <p style={styles.warn}>
          ⚠ Low extraction confidence ({Math.round(status.extraction_confidence * 100)}%) — results may be less accurate. Consider pasting text directly next time.
        </p>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 560,
    margin: "0 auto",
    padding: "32px 40px",
    background: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 6 },
  subtitle: { color: "#555", marginBottom: 24 },
  stepList: { display: "flex", flexDirection: "column", gap: 12 },
  stepRow: { display: "flex", alignItems: "center", gap: 12 },
  dot: { fontSize: 18, width: 24, textAlign: "center", flexShrink: 0 },
  dotDone: { color: "#1a7a1a" },
  dotActive: { color: "#1a73e8" },
  dotPending: { color: "#bbb" },
  stepLabel: { flex: 1, fontSize: 15, color: "#555" },
  labelDone: { color: "#333" },
  labelActive: { color: "#1a1a1a", fontWeight: 600 },
  stepStatus: { fontSize: 12, color: "#888", minWidth: 80, textAlign: "right" },
  warn: {
    marginTop: 20,
    padding: "10px 14px",
    background: "#fffbe6",
    border: "1px solid #ffe58f",
    borderRadius: 6,
    fontSize: 13,
    color: "#7d5a00",
  },
};
