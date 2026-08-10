/**
 * Typed HTTP client for the CareerAgent FastAPI backend.
 * Vite proxies `/api` to the backend (see vite.config.ts), so requests
 * work both in dev and once the built assets are served behind the same host.
 */
import axios from "axios";
import type {
  AchievementSelectionResult,
  BackgroundAnalysisStatusResponse,
  BackgroundAnalysisSubmissionResponse,
  CandidateProfileData,
  CandidateProfileResponse,
  CoverLetterDraft,
  CoverLetterOptions,
  ExportPreferences,
  InterviewPrepPlan,
  JobPostingResponse,
  JobPostingSummary,
  ResumeBuildRequest,
  ResumePlan,
  ScoringResultResponse,
} from "../types/api";

const api = axios.create({
  baseURL: "/api/v1",
});

export default api;

// ---------- Jobs ----------

export async function ingestJobText(payload: {
  raw_text: string;
  title?: string | null;
  company?: string | null;
  source_url?: string | null;
}): Promise<JobPostingResponse> {
  const { data } = await api.post<JobPostingResponse>("/jobs", payload);
  return data;
}

export async function uploadJobFile(
  file: File,
  meta?: { title?: string; company?: string; source_url?: string }
): Promise<JobPostingResponse> {
  const form = new FormData();
  form.append("file", file);
  if (meta?.title) form.append("title", meta.title);
  if (meta?.company) form.append("company", meta.company);
  if (meta?.source_url) form.append("source_url", meta.source_url);
  const { data } = await api.post<JobPostingResponse>("/jobs/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function listJobPostings(): Promise<JobPostingSummary[]> {
  const { data } = await api.get<JobPostingSummary[]>("/jobs");
  return data;
}

export async function getJobPosting(jobId: number): Promise<JobPostingResponse> {
  const { data } = await api.get<JobPostingResponse>(`/jobs/${jobId}`);
  return data;
}

// ---------- Analysis ----------

export async function runAnalysis(jobId: number): Promise<ScoringResultResponse> {
  const { data } = await api.post<ScoringResultResponse>(`/analysis/${jobId}`);
  return data;
}

export async function submitBackgroundAnalysis(
  jobId: number
): Promise<BackgroundAnalysisSubmissionResponse> {
  const { data } = await api.post<BackgroundAnalysisSubmissionResponse>(
    `/analysis/${jobId}/background`
  );
  return data;
}

export async function getAnalysisStatus(
  jobId: number
): Promise<BackgroundAnalysisStatusResponse> {
  const { data } = await api.get<BackgroundAnalysisStatusResponse>(
    `/analysis/${jobId}/status`
  );
  return data;
}

export async function getAnalysis(jobId: number): Promise<ScoringResultResponse> {
  const { data } = await api.get<ScoringResultResponse>(`/analysis/${jobId}`);
  return data;
}

// ---------- Resume ----------

export async function buildResumePlan(
  jobId: number,
  options?: ResumeBuildRequest
): Promise<ResumePlan> {
  const { data } = await api.post<ResumePlan>(`/resume/${jobId}`, {
    boosted_accomplishment_ids: options?.boosted_accomplishment_ids ?? [],
    boost_multiplier: options?.boost_multiplier ?? 1.5,
    top_n: options?.top_n ?? 4,
    export_preferences: options?.export_preferences ?? {
      reactive_resume_template: "onyx",
      reactive_resume_page_format: "letter",
    },
  });
  return data;
}

export async function getResumePlan(jobId: number): Promise<ResumePlan> {
  const { data } = await api.get<ResumePlan>(`/resume/${jobId}`);
  return data;
}

export function resumeDocxDownloadUrl(jobId: number): string {
  return `/api/v1/resume/${jobId}/download/docx`;
}

export function resumePdfDownloadUrl(jobId: number, preferences?: ExportPreferences): string {
  const params = new URLSearchParams();
  if (preferences?.reactive_resume_template) {
    params.set("template", preferences.reactive_resume_template);
  }
  if (preferences?.reactive_resume_page_format) {
    params.set("page_format", preferences.reactive_resume_page_format);
  }
  const query = params.toString();
  return query
    ? `/api/v1/resume/${jobId}/download/pdf?${query}`
    : `/api/v1/resume/${jobId}/download/pdf`;
}

// ---------- Profile ----------

export async function getProfile(): Promise<CandidateProfileResponse> {
  const { data } = await api.get<CandidateProfileResponse>("/profile");
  return data;
}

export async function upsertProfile(
  payload: CandidateProfileData
): Promise<CandidateProfileResponse> {
  const { data } = await api.put<CandidateProfileResponse>("/profile", payload);
  return data;
}

export async function uploadProfile(file: File): Promise<CandidateProfileResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<CandidateProfileResponse>("/profile/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function refreshProfileFromCanonicalFile(): Promise<CandidateProfileResponse> {
  const { data } = await api.post<CandidateProfileResponse>("/profile/refresh");
  return data;
}

// ---------- Interview prep ----------

export async function buildInterviewPrep(jobId: number): Promise<InterviewPrepPlan> {
  const { data } = await api.post<InterviewPrepPlan>(`/interview/${jobId}`);
  return data;
}

export async function getInterviewPrep(jobId: number): Promise<InterviewPrepPlan> {
  const { data } = await api.get<InterviewPrepPlan>(`/interview/${jobId}`);
  return data;
}

// ---------- Cover letters ----------

export async function buildCoverLetter(
  jobId: number,
  options?: CoverLetterOptions
): Promise<CoverLetterDraft> {
  const { data } = await api.post<CoverLetterDraft>(
    `/cover-letters/${jobId}`,
    options ?? { tone: "professional", style: "concise" }
  );
  return data;
}

export function coverLetterDownloadUrl(jobId: number): string {
  return `/api/v1/cover-letters/${jobId}/download`;
}

// ---------- Achievement selection (surfaced via ResumePlan.selection) ----------

export type { AchievementSelectionResult };
