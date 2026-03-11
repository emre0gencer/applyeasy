/** Typed API client for the resume tailor backend. */

const BASE = "/api";

export interface UploadResponse {
  session_id: string;
  message: string;
  detected_format: string;
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

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: formData });
  return handleResponse<UploadResponse>(res);
}

export async function uploadText(text: string): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("text", text);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: formData });
  return handleResponse<UploadResponse>(res);
}

export async function startGeneration(
  sessionId: string,
  jobDescription: string,
  templateId: string = "classic",
  includeCoverLetter: boolean = false
): Promise<GenerateResponse> {
  const res = await fetch(`${BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      job_description: jobDescription,
      template_id: templateId,
      include_cover_letter: includeCoverLetter,
    }),
  });
  return handleResponse<GenerateResponse>(res);
}

export async function getStatus(runId: string): Promise<StatusResponse> {
  const res = await fetch(`${BASE}/status/${runId}`);
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
  const res = await fetch(getDownloadUrl(runId, "summary"));
  return handleResponse<ChangeSummary>(res);
}
