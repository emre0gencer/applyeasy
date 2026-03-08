import { StatusResponse, getDownloadUrl } from "../api/client";

interface Props {
  runId: string;
  status: StatusResponse;
  onRestart: () => void;
}

export function ResultsStep({ runId, status, onRestart }: Props) {
  const flags = status.validation_flags ?? [];
  const coverage = flags.find((f) => f.includes("keyword coverage"));
  const rephrased = flags.find((f) => f.includes("rephrased"));
  const otherFlags = flags.filter((f) => !coverage && !rephrased);

  function download(doc: "resume" | "cover-letter" | "summary") {
    window.open(getDownloadUrl(runId, doc), "_blank");
  }

  return (
    <div style={styles.card}>
      <h2 style={styles.title}>Step 4 of 4: Your Documents</h2>

      <div style={styles.notice}>
        <strong>⚠ Review before submitting</strong> — verify all facts are accurate before sending to an employer.
      </div>

      <div style={styles.downloadSection}>
        <button style={styles.downloadBtn} onClick={() => download("resume")}>
          Download Resume PDF
        </button>
        <button style={styles.downloadBtn} onClick={() => download("cover-letter")}>
          Download Cover Letter PDF
        </button>
        <button style={{ ...styles.downloadBtn, ...styles.secondaryBtn }} onClick={() => download("summary")}>
          Download Change Summary (JSON)
        </button>
      </div>

      {flags.length > 0 && (
        <div style={styles.validationSection}>
          <h3 style={styles.validationTitle}>Validation Notes</h3>
          <ul style={styles.flagList}>
            {flags.map((flag, i) => (
              <li key={i} style={styles.flagItem}>
                <span style={flag.includes("warning") || flag.includes("fabricat") ? styles.flagError : styles.flagWarn}>
                  {flag.includes("warning") || flag.includes("fabricat") ? "✗" : "!"}
                </span>
                {" "}{flag}
              </li>
            ))}
          </ul>
        </div>
      )}

      {flags.length === 0 && (
        <div style={styles.allClear}>
          <p>✓ No validation issues detected</p>
        </div>
      )}

      <div style={styles.checklist}>
        <h3 style={styles.validationTitle}>Before you submit, confirm:</h3>
        <label style={styles.checkItem}><input type="checkbox" /> All job titles and dates are accurate</label>
        <label style={styles.checkItem}><input type="checkbox" /> All metrics and numbers are correct</label>
        <label style={styles.checkItem}><input type="checkbox" /> Cover letter examples are genuine</label>
        <label style={styles.checkItem}><input type="checkbox" /> No skills claimed you don't have</label>
        <label style={styles.checkItem}><input type="checkbox" /> Reviewed the change summary for any rephrasing</label>
      </div>

      <button style={styles.restartBtn} onClick={onRestart}>
        Start a new application
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 600,
    margin: "0 auto",
    padding: "32px 40px",
    background: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 16 },
  notice: {
    padding: "12px 16px",
    background: "#fffbe6",
    border: "1px solid #ffe58f",
    borderRadius: 6,
    fontSize: 14,
    marginBottom: 24,
    color: "#7d5a00",
  },
  downloadSection: { display: "flex", flexDirection: "column", gap: 12, marginBottom: 28 },
  downloadBtn: {
    padding: "12px 24px",
    background: "#1a1a1a",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    fontSize: 15,
    cursor: "pointer",
    fontWeight: 600,
    textAlign: "center",
  },
  secondaryBtn: {
    background: "transparent",
    color: "#333",
    border: "1px solid #ccc",
  },
  validationSection: {
    background: "#f8f8f8",
    border: "1px solid #eee",
    borderRadius: 6,
    padding: "16px 20px",
    marginBottom: 24,
  },
  validationTitle: { fontSize: 15, fontWeight: 600, marginBottom: 10 },
  flagList: { listStyle: "none", padding: 0, margin: 0 },
  flagItem: { fontSize: 13, marginBottom: 6, color: "#444" },
  flagWarn: { color: "#b8860b", fontWeight: 700 },
  flagError: { color: "#c00", fontWeight: 700 },
  allClear: {
    background: "#f0fff4",
    border: "1px solid #b2f5ca",
    borderRadius: 6,
    padding: "12px 16px",
    color: "#1a7a1a",
    fontSize: 14,
    marginBottom: 24,
  },
  checklist: {
    marginBottom: 28,
  },
  checkItem: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 14,
    marginBottom: 8,
    cursor: "pointer",
    color: "#333",
  },
  restartBtn: {
    padding: "8px 20px",
    background: "transparent",
    color: "#555",
    border: "1px solid #ccc",
    borderRadius: 6,
    fontSize: 14,
    cursor: "pointer",
  },
};
