import { useRef, useState } from "react";
import { uploadFile, uploadText } from "../api/client";

interface Props {
  onNext: (sessionId: string) => void;
}

export function ProfileStep({ onNext }: Props) {
  const [mode, setMode] = useState<"file" | "text">("file");
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setLoading(true);
    setError("");
    try {
      const res = await uploadFile(file);
      onNext(res.session_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleText() {
    if (!text.trim()) {
      setError("Please paste your resume text.");
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

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div style={styles.card}>
      <h2 style={styles.title}>Step 1 of 4: Your Profile</h2>
      <p style={styles.subtitle}>Upload a PDF or paste your resume text.</p>

      <div style={styles.tabRow}>
        <button
          style={{ ...styles.tab, ...(mode === "file" ? styles.tabActive : {}) }}
          onClick={() => setMode("file")}
        >
          Upload PDF
        </button>
        <button
          style={{ ...styles.tab, ...(mode === "text" ? styles.tabActive : {}) }}
          onClick={() => setMode("text")}
        >
          Paste Text
        </button>
      </div>

      {mode === "file" ? (
        <div
          style={{
            ...styles.dropZone,
            ...(dragging ? styles.dropZoneActive : {}),
          }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
          <p style={styles.dropText}>
            {loading ? "Uploading..." : "Drop PDF here or click to browse"}
          </p>
          <p style={styles.dropHint}>Accepts .pdf or .txt — max 10 MB</p>
        </div>
      ) : (
        <div>
          <textarea
            style={styles.textarea}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste your full resume here..."
            rows={16}
          />
          <button
            style={styles.primary}
            onClick={handleText}
            disabled={loading}
          >
            {loading ? "Uploading..." : "Next →"}
          </button>
        </div>
      )}

      {error && <p style={styles.error}>{error}</p>}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 640,
    margin: "0 auto",
    padding: "32px 40px",
    background: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 6 },
  subtitle: { color: "#555", marginBottom: 20 },
  tabRow: { display: "flex", gap: 8, marginBottom: 20 },
  tab: {
    padding: "6px 18px",
    border: "1px solid #ccc",
    borderRadius: 4,
    background: "#f5f5f5",
    cursor: "pointer",
    fontSize: 14,
  },
  tabActive: { background: "#1a1a1a", color: "#fff", borderColor: "#1a1a1a" },
  dropZone: {
    border: "2px dashed #ccc",
    borderRadius: 8,
    padding: "40px 20px",
    textAlign: "center",
    cursor: "pointer",
    transition: "border-color 0.2s",
  },
  dropZoneActive: { borderColor: "#1a73e8", background: "#f0f6ff" },
  dropText: { fontSize: 16, fontWeight: 500, marginBottom: 8 },
  dropHint: { fontSize: 12, color: "#888" },
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
  error: { color: "#c00", marginTop: 12, fontSize: 14 },
};
