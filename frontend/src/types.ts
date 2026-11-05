export type Severity = "critical" | "high" | "medium" | "low";
export type FindingCategory =
  | "bug"
  | "security"
  | "performance"
  | "maintainability"
  | "testing"
  | "style";
export type FindingCertainty = "evidence_backed" | "speculative";

export interface PullRequestRequest {
  url: string;
}

export interface Finding {
  file_path: string;
  line_start: number | null;
  line_end: number | null;
  severity: Severity;
  category: FindingCategory;
  title: string;
  explanation: string;
  evidence: string;
  suggested_fix: string;
  confidence: number | null;
  certainty: FindingCertainty;
}

export interface ReviewResponse {
  summary: string;
  findings: Finding[];
  test_suggestions: string[];
}

export interface ReviewResult {
  request: PullRequestRequest;
  review: ReviewResponse;
  status: "completed" | "limited";
  tool_calls: number;
  iterations: number;
  stop_reason: string;
}
