import { useMemo, useState } from "react";
import type { ReviewResult, Severity } from "../types";
import { FindingCard } from "./FindingCard";

const severityOrder: Severity[] = ["critical", "high", "medium", "low"];
const severityIcons: Record<Severity, string> = { critical: "!", high: "↑", medium: "•", low: "↓" };

function parsePullRequest(url: string) {
  const match = url.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/i);
  return match ? { owner: match[1], repository: match[2], number: match[3] } : null;
}

function stopReasonLabel(value: string): string {
  return value.replaceAll("_", " ");
}

export function ReviewDashboard({ result }: { result: ReviewResult }) {
  const [activeSeverity, setActiveSeverity] = useState<Severity | "all">("all");
  const pr = parsePullRequest(result.request.url);
  const counts = useMemo(
    () => Object.fromEntries(severityOrder.map((severity) => [severity, result.review.findings.filter((finding) => finding.severity === severity).length])) as Record<Severity, number>,
    [result.review.findings],
  );
  const visibleFindings = activeSeverity === "all" ? result.review.findings : result.review.findings.filter((finding) => finding.severity === activeSeverity);

  return (
    <section className="results-section" aria-live="polite">
      <div className="review-context-card"><div className="repo-avatar">{pr?.repository.slice(0, 1).toUpperCase() ?? "P"}</div><div className="review-context-main"><div className="review-breadcrumb"><span>{pr ? `${pr.owner} / ${pr.repository}` : "GitHub pull request"}</span>{pr && <><span className="breadcrumb-slash">/</span><span>pull request #{pr.number}</span></>}</div><h2>AI review report</h2><a href={result.request.url} target="_blank" rel="noreferrer" className="context-url">{result.request.url} ↗</a></div><div className={`status-pill ${result.status}`}><span className="status-dot" />{result.status}</div></div>
      <div className="review-summary"><div className="summary-icon">✦</div><div><span className="eyebrow">Executive summary</span><p>{result.review.summary}</p></div></div>
      <div className="metrics-grid"><div className="metric-card total"><span className="metric-label">Total findings</span><strong>{result.review.findings.length}</strong><span className="metric-note">evidence-reviewed issues</span></div>{severityOrder.map((severity) => <button className={`metric-card ${severity} ${activeSeverity === severity ? "selected" : ""}`} key={severity} onClick={() => setActiveSeverity(activeSeverity === severity ? "all" : severity)} aria-pressed={activeSeverity === severity}><span className="metric-icon">{severityIcons[severity]}</span><span className="metric-label">{severity}</span><strong>{counts[severity]}</strong><span className="metric-note">{counts[severity] === 1 ? "finding" : "findings"}</span></button>)}</div>
      <div className="results-grid"><div className="findings-column"><div className="section-heading"><div><span className="eyebrow">Evidence-backed review</span><h2>{result.review.findings.length ? "Findings" : "No issues found"}</h2></div><div className="filter-group" role="group" aria-label="Filter findings by severity"><button className={activeSeverity === "all" ? "active" : ""} onClick={() => setActiveSeverity("all")}>All <span>{result.review.findings.length}</span></button>{severityOrder.filter((severity) => counts[severity] > 0).map((severity) => <button key={severity} className={activeSeverity === severity ? "active" : ""} onClick={() => setActiveSeverity(severity)}>{severity} <span>{counts[severity]}</span></button>)}</div></div>{visibleFindings.length ? visibleFindings.map((finding, index) => <FindingCard key={`${finding.file_path}-${finding.line_start}-${index}`} finding={finding} index={index} prUrl={result.request.url} />) : <div className="clean-state"><span>✓</span><div><strong>{activeSeverity === "all" ? "Clean review surface" : `No ${activeSeverity} findings`}</strong><p>{activeSeverity === "all" ? "The agent did not identify a supported issue in the changed files." : "Try another severity filter or view all findings."}</p></div></div>}</div>
        <aside className="insight-rail"><div className="rail-card"><div className="rail-heading"><span className="rail-icon">⌘</span><div><span className="eyebrow">Test strategy</span><h3>Suggested coverage</h3></div></div>{result.review.test_suggestions.length ? <ul>{result.review.test_suggestions.map((suggestion, index) => <li key={index}><span>{String(index + 1).padStart(2, "0")}</span>{suggestion}</li>)}</ul> : <p className="muted">No additional test suggestions were returned.</p>}</div><div className="rail-card telemetry"><div className="rail-heading"><span className="rail-icon">◌</span><div><span className="eyebrow">Agent telemetry</span><h3>Execution trace</h3></div></div><div className="telemetry-row"><span>Tool calls</span><strong>{result.tool_calls}</strong></div><div className="telemetry-row"><span>Iterations</span><strong>{result.iterations}</strong></div><div className="telemetry-row"><span>Execution status</span><strong className="telemetry-status">{result.status}</strong></div><div className="telemetry-row"><span>Stop reason</span><strong>{stopReasonLabel(result.stop_reason)}</strong></div></div></aside>
      </div>
    </section>
  );
}
