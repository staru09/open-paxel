export interface InsightCard {
  id: string;
  title: string;
  value: string;
  subtitle?: string | null;
  question?: string | null;
}

export interface ProfileNarrative {
  narrative: string;
  what_you_built: string;
  decision_patterns: string;
  matched_pattern?: string | null;
  matched_pattern_category?: string | null;
  strengths: string[];
  growth_areas: string[];
}

export interface BuilderProfile {
  updated_at: string;
  session_count: number;
  upload_count: number;
  dimensions: Record<string, number>;
  archetype: string;
  archetype_counts: Record<string, number>;
  signature_moves: string[];
  growth_edge: string[];
  insight_cards: InsightCard[];
  narrative?: ProfileNarrative | null;
}

export interface SessionSummary {
  session_id: string;
  title?: string | null;
  project_path?: string | null;
  analyzed_at: string;
  archetype: string;
  dimensions: Record<string, number>;
}

export interface DimensionScore {
  score: number;
  narrative: string;
  evidence: string[];
}

export interface SessionReport {
  session_id: string;
  title?: string | null;
  project_path?: string | null;
  analyzed_at: string;
  archetype: string;
  dimensions: Record<string, DimensionScore>;
  signature_moves: string[];
  growth_edge: string[];
}

export interface UploadReport {
  id: string;
  created_at: string;
  session_count: number;
  project_paths: string[];
  session_ids: string[];
}

export interface UploadFileResult {
  filename: string;
  status: string;
  session_id?: string | null;
  title?: string | null;
  error?: string | null;
}

export interface UploadResponse {
  upload_id: string | null;
  session_count: number;
  succeeded: number;
  failed: number;
  results: UploadFileResult[];
  job_id?: string | null;
}

export interface UploadJobStart {
  job_id: string;
  status: string;
  total_count: number;
}

export interface OpenAICallRecord {
  phase: string;
  model: string;
  status: string;
  duration_ms?: number;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  request_id?: string | null;
  detail?: string | null;
  chunk_index?: number | null;
  chunk_total?: number | null;
}

export interface ProcessingJob {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  force: boolean;
  total_count: number;
  succeeded: number;
  failed: number;
  current_file: string | null;
  current_step: string | null;
  results: UploadFileResult[];
  upload_id: string | null;
  logs: string[];
  openai_calls: OpenAICallRecord[];
}

const base = "";

/** Static demo build (GitHub Pages): read pre-generated JSON instead of the API. */
export const DEMO = import.meta.env.VITE_DEMO === "1";
const demoUrl = (path: string) => `${import.meta.env.BASE_URL}api/${path}.json`;

export async function fetchProfile(): Promise<BuilderProfile> {
  const r = await fetch(DEMO ? demoUrl("profile") : `${base}/api/profile`);
  if (!r.ok) throw new Error("Failed to load profile");
  return r.json();
}

export async function fetchSessions(limit = 50): Promise<{ items: SessionSummary[] }> {
  const r = await fetch(DEMO ? demoUrl("sessions") : `${base}/api/sessions?limit=${limit}`);
  if (!r.ok) throw new Error("Failed to load sessions");
  return r.json();
}

export async function fetchSession(id: string): Promise<SessionReport> {
  const r = await fetch(DEMO ? demoUrl(`sessions/${id}`) : `${base}/api/sessions/${id}`);
  if (!r.ok) throw new Error("Session not found");
  return r.json();
}

export async function updateSessionTitle(sessionId: string, title: string): Promise<SessionReport> {
  const r = await fetch(`${base}/api/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!r.ok) throw new Error("Failed to rename session");
  return r.json();
}

export async function fetchUploads(): Promise<UploadReport[]> {
  const r = await fetch(`${base}/api/uploads`);
  if (!r.ok) throw new Error("Failed to load uploads");
  return r.json();
}

export async function uploadSessionFiles(files: File[], force = false): Promise<UploadJobStart> {
  const body = new FormData();
  for (const file of files) {
    body.append("files", file);
  }
  const r = await fetch(`${base}/api/upload?force=${force}`, {
    method: "POST",
    body,
  });
  if (!r.ok) {
    let detail = "Upload failed";
    try {
      const err = await r.json();
      detail = err.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : "Upload failed");
  }
  if (r.status === 202) {
    return r.json();
  }
  const full = (await r.json()) as UploadResponse;
  return {
    job_id: full.job_id ?? "",
    status: "completed",
    total_count: full.succeeded + full.failed,
  };
}

export async function fetchActiveJobs(): Promise<ProcessingJob[]> {
  if (DEMO) return [];
  const r = await fetch(`${base}/api/jobs?active=true`);
  if (!r.ok) throw new Error("Failed to load active jobs");
  return r.json();
}

export async function fetchJob(jobId: string): Promise<ProcessingJob> {
  const r = await fetch(`${base}/api/jobs/${jobId}`);
  if (!r.ok) throw new Error("Job not found");
  return r.json();
}

export async function fetchRecentJobs(limit = 10): Promise<ProcessingJob[]> {
  const r = await fetch(`${base}/api/jobs?limit=${limit}`);
  if (!r.ok) throw new Error("Failed to load jobs");
  return r.json();
}
