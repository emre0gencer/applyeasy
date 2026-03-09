import { useState } from "react";
import { uploadText } from "../api/client";

interface Props {
  onNext: (sessionId: string) => void;
}

export function ProfileStep({ onNext }: Props) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    if (!text.trim()) {
      setError("Please paste your background information.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await uploadText(text);
      onNext(res.session_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.card}>
      <h2 style={styles.title}>Step 1 of 4: Your Background</h2>
      <p style={styles.subtitle}>
        Paste anything professionally or academically relevant — work history,
        projects, skills, education, links, certifications. The more you include,
        the better the tailoring.
      </p>

      <textarea
        style={styles.textarea}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={
          "Jane Smith\njane@email.com | (555) 123-4567 | linkedin.com/in/janesmith | github.com/janesmith\n\nSoftware Engineer at Acme Corp (Jan 2022 – Present)\n- Built Kafka pipeline processing 2M events/day\n...\n\nB.S. Computer Science, UC Berkeley, 2020\n\nSkills: Python, FastAPI, React, PostgreSQL, Docker"
        }
        rows={18}
      />

      {error && <p style={styles.error}>{error}</p>}

      <button
        style={{ ...styles.primary, ...(loading ? styles.primaryDisabled : {}) }}
        onClick={handleSubmit}
        disabled={loading}
      >
        {loading ? "Processing..." : "Next →"}
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 660,
    margin: "0 auto",
    padding: "32px 40px",
    background: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 6 },
  subtitle: { color: "#555", marginBottom: 20, fontSize: 14, lineHeight: 1.5 },
  textarea: {
    width: "100%",
    padding: "12px",
    border: "1px solid #ddd",
    borderRadius: 6,
    fontSize: 13,
    fontFamily: "monospace",
    resize: "vertical",
    boxSizing: "border-box",
    marginBottom: 16,
    lineHeight: 1.5,
  },
  primary: {
    padding: "10px 28px",
    background: "#1a1a1a",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    fontSize: 15,
    cursor: "pointer",
    fontWeight: 600,
  },
  primaryDisabled: {
    background: "#888",
    cursor: "not-allowed",
  },
  error: { color: "#c00", marginTop: 0, marginBottom: 12, fontSize: 14 },
};
