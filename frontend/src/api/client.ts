/** Typed API client for the resume tailor backend. */

const BASE = "/api";

export interface UploadResponse {
  session_id: string;
  message: string;
  detected_format: string;
}

export interface Bullet {
  text: string;
  source_text: string;
  relevance_scores?: Record<string, number>;
}

export interface ExperienceEntry {
  company: string;
  role_title: string;
  start_date: string;
  end_date?: string;
  location?: string;
  bullets: Bullet[];
  source_text: string;
}

export interface EducationEntry {
  institution: string;
  degree?: string;
  field_of_study?: string;
  graduation_date?: string;
  gpa?: string;
  honors: string[];
  coursework?: string;
  source_text: string;
}

export interface ProjectEntry {
  name: string;
  description: string;
  technologies: string[];
  url?: string;
  date?: string;
  bullets: Bullet[];
  source_text: string;
  relevance_score?: number;
}

export interface Skill {
  name: string;
  category?: string;
  source_text: string;
}

export interface CandidateProfile {
  profile_id: string;
  name: string;
  email?: string;
  phone?: string;
  linkedin?: string;
  github?: string;
  location?: string;
  summary?: string;
  experiences: ExperienceEntry[];
  education: EducationEntry[];
  projects: ProjectEntry[];
  skills: Skill[];
  awards: Array<{ title: string; issuer?: string; date?: string; description?: string; source_text: string }>;
  leadership_items: string[];
  source_documents: string[];
  extraction_confidence: number;
  raw_text: string;
}

export interface ProfileGap {
  code: string;
  path: string;
  message: string;
  severity: "info" | "warning" | "error";
}

export interface ProfileReviewResponse {
  session_id: string;
  profile: CandidateProfile;
  gaps: ProfileGap[];
  message?: string;
}

export interface GenerateResponse {
  run_id: string;
  message: string;
}

export interface StatusResponse {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress_step: string;
  progress_message: string;
  validation_flags: string[];
  error_message?: string;
  extraction_confidence?: number;
  keyword_coverage?: number;
  experience_count?: number;
  raw_suitability_score?: number;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// All requests include credentials so the HttpOnly ownership cookie set on
// /upload is sent back on /generate, /status, and /download (IDOR protection).
export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: formData, credentials: "include" });
  return handleResponse<UploadResponse>(res);
}

export async function uploadText(text: string): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("text", text);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: formData, credentials: "include" });
  return handleResponse<UploadResponse>(res);
}

export async function normalizeProfile(
  sessionId: string,
  tier: "standard" | "pro" = "standard"
): Promise<ProfileReviewResponse> {
  const res = await fetch(`${BASE}/profile/${sessionId}/normalize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ tier }),
  });
  return handleResponse<ProfileReviewResponse>(res);
}

export async function saveProfile(
  sessionId: string,
  profile: CandidateProfile
): Promise<ProfileReviewResponse> {
  const res = await fetch(`${BASE}/profile/${sessionId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ profile }),
  });
  return handleResponse<ProfileReviewResponse>(res);
}

export async function startGeneration(
  sessionId: string,
  jobDescription: string,
  templateId: string = "classic",
  includeCoverLetter: boolean = false,
  tier: "standard" | "pro" = "standard"
): Promise<GenerateResponse> {
  const res = await fetch(`${BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      session_id: sessionId,
      job_description: jobDescription,
      template_id: templateId,
      include_cover_letter: includeCoverLetter,
      tier,
    }),
  });
  return handleResponse<GenerateResponse>(res);
}

export async function getStatus(runId: string): Promise<StatusResponse> {
  const res = await fetch(`${BASE}/status/${runId}`, { credentials: "include" });
  return handleResponse<StatusResponse>(res);
}

export function getDownloadUrl(runId: string, doc: "resume" | "cover-letter" | "summary"): string {
  return `${BASE}/download/${runId}/${doc}`;
}

export interface BulletChange {
  original_text: string;
  revised_text: string;
  change_reason: string;
  keywords_added: string[];
}

export interface ChangeSummary {
  run_id: string;
  profile_name: string;
  role_title: string;
  company_name: string;
  bullet_changes: BulletChange[];
  keywords_integrated: string[];
}

export async function fetchChangeSummary(runId: string): Promise<ChangeSummary> {
  const res = await fetch(getDownloadUrl(runId, "summary"), { credentials: "include" });
  return handleResponse<ChangeSummary>(res);
}
