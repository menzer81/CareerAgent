/**
 * TypeScript mirrors of the Pydantic schemas in app/schemas/*.py.
 * Keep these in sync with the backend when the API changes.
 */

export interface JobPostingResponse {
  id: number;
  title: string | null;
  company: string | null;
  source_url: string | null;
  raw_text: string;
  ingested_at: string;
}

export interface JobPostingSummary {
  id: number;
  title: string | null;
  company: string | null;
  source_url: string | null;
  ingested_at: string;
}

export type Recommendation =
  | "Strong Apply"
  | "Apply"
  | "Stretch Opportunity"
  | "Low Priority";

export interface DimensionScore {
  score: number;
  explanation: string;
  matched: string[];
  missing: string[];
}

export interface ScoringBreakdown {
  leadership_match: DimensionScore;
  technical_match: DimensionScore;
  cloud_match: DimensionScore;
  ai_match: DimensionScore;
  management_scope_match: DimensionScore;
  industry_match: DimensionScore;
  overall_score: number;
  recommendation: Recommendation;
  recommendation_reasoning: string;
}

export interface GapAnalysis {
  missing_experiences: string[];
  missing_keywords: string[];
  missing_certifications: string[];
  missing_leadership_signals: string[];
  strengths: string[];
  risks: string[];
  resume_focus_areas: string[];
}

export interface FullAnalysisResult {
  job_posting_id: number;
  scoring: ScoringBreakdown;
  gap_analysis: GapAnalysis;
}

export interface ScoringResultResponse {
  id: number;
  job_posting_id: number;
  scoring_data: FullAnalysisResult;
  scored_at: string;
}

export interface BackgroundAnalysisSubmissionResponse {
  job_posting_id: number;
  status: string;
  message: string;
  poll_url: string;
}

export interface BackgroundAnalysisStatusResponse {
  job_posting_id: number;
  status: string;
  message: string;
  result_ready: boolean;
  error: string | null;
}

export type ResumePersona =
  | "AI Transformation Leader"
  | "Engineering Turnaround Specialist"
  | "Compliance & Governance Leader"
  | "Technical Delivery Leader"
  | "Growth Engineering Leader"
  | "Cloud Transformation Leader"
  | "Director Track Candidate";

export interface AccomplishmentRanking {
  id: string;
  ranking_score: number;
  ranking_reason: string[];
  boosted: boolean;
  boost_multiplier: number;
}

export interface AchievementSelectionResult {
  job_posting_id: number;
  rankings: AccomplishmentRanking[];
  selected_accomplishment_ids: string[];
  boosted_accomplishment_ids: string[];
  boost_multiplier: number;
}

export interface ResumeStrategy {
  job_posting_id: number;
  persona: ResumePersona;
  recommended_persona?: ResumePersona | null;
  key_themes: string[];
  emphasize: string[];
  deemphasize: string[];
  omit: string[];
  boosted_accomplishment_ids: string[];
  boost_multiplier: number;
}

export interface KeywordCoverageReport {
  required_keywords: number;
  covered_keywords: number;
  coverage_percent: number;
  matched_keywords: string[];
  missing_keywords: string[];
}

export interface ResumeDataModel {
  job_posting_id: number;
  executive_summary: string;
  selected_work_history: string[];
  selected_accomplishments: string[];
  skills_to_highlight: string[];
  keywords_to_include: string[];
  roles_to_shorten: string[];
  resume_length: string;
}

export interface ResumeQualityScore {
  keyword_coverage: number;
  leadership_signal_strength: number;
  ai_relevance: number;
  manager_of_managers_alignment: number;
  overall_resume_quality: number;
}

export interface ExportPreferences {
  reactive_resume_template: string;
  reactive_resume_page_format: string;
}

export interface ExportCapabilities {
  pdf_renderer: string;
  docx_renderer: string;
  reactive_resume_configured: boolean;
}

export interface ResumeBuildRequest {
  boosted_accomplishment_ids?: string[];
  boost_multiplier?: number;
  top_n?: number;
  persona_override?: ResumePersona;
  export_preferences?: ExportPreferences;
}

export interface ResumePlan {
  job_posting_id: number;
  selection: AchievementSelectionResult;
  strategy: ResumeStrategy;
  keyword_coverage: KeywordCoverageReport;
  data_model: ResumeDataModel;
  quality_score: ResumeQualityScore;
  export_preferences: ExportPreferences;
  export_capabilities: ExportCapabilities;
  markdown: string;
}

export interface InterviewQuestion {
  category: string;
  question: string;
  rationale: string;
  talking_points: string[];
}

export interface InterviewPrepPlan {
  job_posting_id: number;
  recommendation: Recommendation;
  overall_score: number;
  opening_pitch: string;
  priority_focus_areas: string[];
  likely_questions: InterviewQuestion[];
  risk_mitigation_points: string[];
  questions_to_ask_interviewer: string[];
}

export type CoverLetterTone = "professional" | "confident" | "conversational";
export type CoverLetterStyle = "concise" | "executive" | "storytelling";

export interface CoverLetterOptions {
  tone: CoverLetterTone;
  style: CoverLetterStyle;
}

export interface CoverLetterDraft {
  job_posting_id: number;
  persona: ResumePersona;
  tone: CoverLetterTone;
  style: CoverLetterStyle;
  subject_line: string;
  greeting: string;
  opening_paragraph: string;
  body_paragraphs: string[];
  closing_paragraph: string;
  signature: string;
  markdown: string;
}

export interface CandidateProfileData {
  full_name: string;
  current_title?: string;
  [key: string]: unknown;
}

export interface CandidateProfileResponse {
  id: number;
  full_name: string;
  profile_data: CandidateProfileData;
}
