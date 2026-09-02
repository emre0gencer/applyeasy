import { useEffect, useState } from "react";
import {
  CandidateProfile,
  normalizeProfile,
  ProfileGap,
  saveProfile,
} from "../api/client";

interface Props {
  sessionId: string;
  onBack: () => void;
  onNext: (profile: CandidateProfile) => void;
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "10px 12px",
  borderRadius: 7,
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(255,255,255,0.04)",
  color: "#e2e8f0",
  font: "inherit",
  fontSize: 13,
  outline: "none",
};

export function ProfileReviewStep({ sessionId, onBack, onNext }: Props) {
  const [profile, setProfile] = useState<CandidateProfile>();
  const [gaps, setGaps] = useState<ProfileGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    normalizeProfile(sessionId)
      .then((result) => {
        if (!active) return;
        setProfile(result.profile);
        setGaps(result.gaps);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not normalize profile");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [sessionId]);

  function patch(values: Partial<CandidateProfile>) {
    setProfile((current) => current ? { ...current, ...values } : current);
  }

  async function handleContinue() {
    if (!profile) return;
    setSaving(true);
    setError("");
    try {
      const result = await saveProfile(sessionId, profile);
      setGaps(result.gaps);
      onNext(result.profile);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not save profile");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div style={styles.card}><p style={styles.loading}>Structuring your profile for review…</p></div>;
  }
  if (!profile) {
    return (
      <div style={styles.card}>
        <p style={styles.error}>{error || "No profile data was extracted."}</p>
        <button style={styles.secondary} onClick={onBack}>← Back</button>
      </div>
    );
  }

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>Review your profile</h2>
          <p style={styles.subtitle}>Correct anything that was parsed incorrectly. Your edits become the verified source for generation.</p>
        </div>
        <span style={styles.confidence}>{Math.round(profile.extraction_confidence * 100)}% parse confidence</span>
      </div>

      {gaps.length > 0 && (
        <div style={styles.gapBox}>
          <strong style={styles.gapTitle}>{gaps.length} item{gaps.length === 1 ? "" : "s"} to review</strong>
          {gaps.slice(0, 8).map((gap, index) => (
            <div key={`${gap.path}-${index}`} style={styles.gapLine}>
              <span style={{ color: gap.severity === "error" ? "#fca5a5" : gap.severity === "warning" ? "#fcd34d" : "#93c5fd" }}>●</span>
              {gap.message}
            </div>
          ))}
        </div>
      )}

      <Section title="Contact">
        <div style={styles.grid2}>
          <Field label="Name" value={profile.name} onChange={(name) => patch({ name })} />
          <Field label="Email" value={profile.email ?? ""} onChange={(email) => patch({ email })} />
          <Field label="Phone" value={profile.phone ?? ""} onChange={(phone) => patch({ phone })} />
          <Field label="Location" value={profile.location ?? ""} onChange={(location) => patch({ location })} />
          <Field label="LinkedIn" value={profile.linkedin ?? ""} onChange={(linkedin) => patch({ linkedin })} />
          <Field label="GitHub" value={profile.github ?? ""} onChange={(github) => patch({ github })} />
        </div>
        <label style={styles.label}>Summary</label>
        <textarea style={{ ...inputStyle, minHeight: 76, resize: "vertical" }} value={profile.summary ?? ""} onChange={(event) => patch({ summary: event.target.value })} />
      </Section>

      <Section title="Experience">
        {profile.experiences.map((experience, index) => (
          <div style={styles.entry} key={`${experience.company}-${index}`}>
            <div style={styles.grid2}>
              <Field label="Role" value={experience.role_title} onChange={(role_title) => patch({ experiences: profile.experiences.map((item, i) => i === index ? { ...item, role_title } : item) })} />
              <Field label="Company" value={experience.company} onChange={(company) => patch({ experiences: profile.experiences.map((item, i) => i === index ? { ...item, company } : item) })} />
              <Field label="Start date" value={experience.start_date} onChange={(start_date) => patch({ experiences: profile.experiences.map((item, i) => i === index ? { ...item, start_date } : item) })} />
              <Field label="End date" value={experience.end_date ?? ""} onChange={(end_date) => patch({ experiences: profile.experiences.map((item, i) => i === index ? { ...item, end_date } : item) })} />
            </div>
            <label style={styles.label}>Accomplishments (one per line)</label>
            <textarea
              style={{ ...inputStyle, minHeight: 92, resize: "vertical" }}
              value={experience.bullets.map((bullet) => bullet.text).join("\n")}
              onChange={(event) => {
                const bullets = event.target.value.split("\n").filter(Boolean).map((text, bulletIndex) => ({
                  text,
                  source_text: experience.bullets[bulletIndex]?.source_text || text,
                }));
                patch({ experiences: profile.experiences.map((item, i) => i === index ? { ...item, bullets } : item) });
              }}
            />
          </div>
        ))}
        <button style={styles.addButton} onClick={() => patch({ experiences: [...profile.experiences, { company: "", role_title: "", start_date: "", bullets: [], source_text: "" }] })}>+ Add experience</button>
      </Section>

      <Section title="Education">
        {profile.education.map((education, index) => (
          <div style={styles.grid2} key={`${education.institution}-${index}`}>
            <Field label="Institution" value={education.institution} onChange={(institution) => patch({ education: profile.education.map((item, i) => i === index ? { ...item, institution } : item) })} />
            <Field label="Degree" value={education.degree ?? ""} onChange={(degree) => patch({ education: profile.education.map((item, i) => i === index ? { ...item, degree } : item) })} />
            <Field label="Field of study" value={education.field_of_study ?? ""} onChange={(field_of_study) => patch({ education: profile.education.map((item, i) => i === index ? { ...item, field_of_study } : item) })} />
            <Field label="Graduation date" value={education.graduation_date ?? ""} onChange={(graduation_date) => patch({ education: profile.education.map((item, i) => i === index ? { ...item, graduation_date } : item) })} />
          </div>
        ))}
        <button style={styles.addButton} onClick={() => patch({ education: [...profile.education, { institution: "", honors: [], source_text: "" }] })}>+ Add education</button>
      </Section>

      <Section title="Projects">
        {profile.projects.map((project, index) => (
          <div style={styles.entry} key={`${project.name}-${index}`}>
            <div style={styles.grid2}>
              <Field label="Project" value={project.name} onChange={(name) => patch({ projects: profile.projects.map((item, i) => i === index ? { ...item, name } : item) })} />
              <Field label="Date" value={project.date ?? ""} onChange={(date) => patch({ projects: profile.projects.map((item, i) => i === index ? { ...item, date } : item) })} />
            </div>
            <Field label="Description" value={project.description} onChange={(description) => patch({ projects: profile.projects.map((item, i) => i === index ? { ...item, description } : item) })} />
            <Field label="Technologies (comma-separated)" value={project.technologies.join(", ")} onChange={(value) => patch({ projects: profile.projects.map((item, i) => i === index ? { ...item, technologies: value.split(",").map((part) => part.trim()).filter(Boolean) } : item) })} />
          </div>
        ))}
        <button style={styles.addButton} onClick={() => patch({ projects: [...profile.projects, { name: "", description: "", technologies: [], bullets: [], source_text: "" }] })}>+ Add project</button>
      </Section>

      <Section title="Skills">
        <Field label="Skills (comma-separated)" value={profile.skills.map((skill) => skill.name).join(", ")} onChange={(value) => patch({ skills: value.split(",").map((name) => name.trim()).filter(Boolean).map((name) => ({ name, source_text: name })) })} />
      </Section>

      {error && <p style={styles.error}>{error}</p>}
      <div style={styles.actions}>
        <button style={styles.secondary} onClick={onBack} disabled={saving}>← Back</button>
        <button style={styles.primary} onClick={handleContinue} disabled={saving}>{saving ? "Saving…" : "Save & continue →"}</button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section style={styles.section}><h3 style={styles.sectionTitle}>{title}</h3>{children}</section>;
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label style={styles.field}><span style={styles.label}>{label}</span><input style={inputStyle} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

const styles: Record<string, React.CSSProperties> = {
  card: { maxWidth: 900, margin: "0 auto", padding: "34px 42px", background: "rgba(2,15,36,0.88)", border: "1px solid rgba(255,255,255,0.09)", borderRadius: 14, color: "#e2e8f0" },
  header: { display: "flex", justifyContent: "space-between", gap: 24, alignItems: "flex-start" },
  title: { margin: "0 0 6px", fontSize: 25 },
  subtitle: { margin: 0, color: "#64748b", fontSize: 14, lineHeight: 1.5 },
  confidence: { flexShrink: 0, color: "#93c5fd", background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 100, padding: "6px 10px", fontSize: 11 },
  loading: { color: "#94a3b8", textAlign: "center", padding: 40 },
  gapBox: { marginTop: 24, padding: "14px 16px", background: "rgba(245,158,11,0.07)", border: "1px solid rgba(245,158,11,0.18)", borderRadius: 8 },
  gapTitle: { display: "block", color: "#f8fafc", fontSize: 13, marginBottom: 8 },
  gapLine: { display: "flex", gap: 8, color: "#94a3b8", fontSize: 12, lineHeight: 1.7 },
  section: { marginTop: 28, paddingTop: 22, borderTop: "1px solid rgba(255,255,255,0.08)" },
  sectionTitle: { margin: "0 0 14px", fontSize: 14, textTransform: "uppercase", letterSpacing: "0.08em", color: "#60a5fa" },
  grid2: { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 },
  field: { display: "block", marginBottom: 12 },
  label: { display: "block", color: "#64748b", fontSize: 11, fontWeight: 700, marginBottom: 5 },
  entry: { marginBottom: 18, padding: 16, background: "rgba(255,255,255,0.025)", borderRadius: 8 },
  error: { color: "#fca5a5", fontSize: 13 },
  actions: { display: "flex", justifyContent: "space-between", marginTop: 30 },
  primary: { padding: "12px 28px", background: "#2563eb", border: 0, borderRadius: 8, color: "white", cursor: "pointer", fontWeight: 700 },
  secondary: { padding: "11px 22px", background: "transparent", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, color: "#94a3b8", cursor: "pointer" },
  addButton: { padding: "8px 12px", background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 7, color: "#93c5fd", cursor: "pointer", fontSize: 12 },
};
