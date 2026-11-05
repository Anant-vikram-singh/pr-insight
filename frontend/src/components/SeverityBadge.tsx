import type { Severity } from "../types";

const severityLabels: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

const severityGlyphs: Record<Severity, string> = {
  critical: "!",
  high: "↑",
  medium: "•",
  low: "↓",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`severity-badge severity-${severity}`}>
      <span className="severity-glyph" aria-hidden="true">{severityGlyphs[severity]}</span>
      {severityLabels[severity]}
    </span>
  );
}
