import { useState } from "react";
import type { Finding } from "../types";
import { SeverityBadge } from "./SeverityBadge";

function normalizeEvidence(value: string): string {
  let evidence = value;
  try {
    const parsed: unknown = JSON.parse(value);
    if (typeof parsed === "string") evidence = parsed;
  } catch {
    // Evidence is allowed to be ordinary prose or code, not only JSON.
  }
  return evidence.replaceAll("\\r\\n", "\n").replaceAll("\\n", "\n").replaceAll("\\t", "\t");
}

function lineLabel(finding: Finding): string {
  if (!finding.line_start) return "Diff line unavailable";
  return finding.line_end && finding.line_end !== finding.line_start
    ? `Lines ${finding.line_start}–${finding.line_end}`
    : `Line ${finding.line_start}`;
}

function evidenceLines(finding: Finding): Array<{ number: number | null; text: string }> {
  return normalizeEvidence(finding.evidence).split("\n").map((text, index) => ({
    number: finding.line_start ? finding.line_start + index : null,
    text,
  }));
}

function githubReference(prUrl: string, finding: Finding): string {
  const path = encodeURIComponent(finding.file_path);
  const line = finding.line_start ? `#L${finding.line_start}` : "";
  return `${prUrl.replace(/\/$/, "")}/files?path=${path}${line}`;
}

export function FindingCard({ finding, index, prUrl }: { finding: Finding; index: number; prUrl: string }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const confidence = finding.confidence === null ? null : Math.round(finding.confidence * 100);
  const codeLines = evidenceLines(finding);

  return (
    <article className={`finding-card ${isExpanded ? "is-expanded" : "is-collapsed"}`}>
      <button className="finding-toggle" onClick={() => setIsExpanded((open) => !open)} aria-expanded={isExpanded}>
        <span className="finding-index">{String(index + 1).padStart(2, "0")}</span>
        <span className="finding-title-wrap">
          <span className="finding-meta"><SeverityBadge severity={finding.severity} /><span className="category-label">{finding.category}</span><span className={`certainty ${finding.certainty}`}>{finding.certainty.replace("_", " ")}</span></span>
          <strong className="finding-title">{finding.title}</strong>
        </span>
        {confidence !== null && <span className="confidence" title="Model confidence, not a correctness guarantee"><strong>{confidence}%</strong><span>confidence</span></span>}
        <span className="collapse-chevron" aria-hidden="true">{isExpanded ? "⌃" : "⌄"}</span>
      </button>
      <div className="finding-location"><code>{finding.file_path}</code><span>{lineLabel(finding)}</span><a href={githubReference(prUrl, finding)} target="_blank" rel="noreferrer">Open on GitHub ↗</a></div>
      {isExpanded && <div className="finding-body">
        <p className="finding-explanation">{finding.explanation}</p>
        <section className="evidence-panel"><div className="panel-heading"><span className="panel-label"><span className="panel-dot evidence-dot" />Evidence from diff</span><span className="panel-hint">{finding.line_start ? "line referenced" : "no line reference returned"}</span></div><pre className="evidence-code" aria-label="Evidence from pull request diff"><code>{codeLines.map((line, lineIndex) => <span className="code-line" key={lineIndex}><span className="code-line-number">{line.number ?? "·"}</span><span className="code-line-text">{line.text || " "}</span></span>)}</code></pre></section>
        <section className="fix-panel"><div className="panel-heading"><span className="panel-label"><span className="panel-dot fix-dot" />Suggested fix</span></div><p>{finding.suggested_fix}</p></section>
      </div>}
    </article>
  );
}
