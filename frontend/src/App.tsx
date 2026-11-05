import { useState, type FormEvent } from "react";
import { Logo } from "./components/Logo";
import { ReviewDashboard } from "./components/ReviewDashboard";
import { createReview } from "./services/reviewApi";
import type { ReviewResult } from "./types";
import "./styles.css";

const GITHUB_PR_PATTERN = /^https:\/\/github\.com\/[^/\s]+\/[^/\s]+\/pull\/\d+\/?$/i;

export default function App() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const trimmedUrl = url.trim();
    if (!GITHUB_PR_PATTERN.test(trimmedUrl)) {
      setError("Enter a public GitHub pull request URL, for example https://github.com/org/repo/pull/123.");
      return;
    }
    setIsLoading(true);
    try { setResult(await createReview(trimmedUrl)); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The review could not be completed."); } finally { setIsLoading(false); }
  }

  function reset() { setResult(null); setError(""); setUrl(""); }

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" /><div className="ambient ambient-two" />
      <header className="topbar"><Logo /><div className="topbar-status"><span className="status-dot" />AI review engine <span className="divider" /><span className="version">MVP · live backend</span></div></header>
      <main className="main-content">
        {!result ? <section className="hero"><div className="hero-kicker"><span className="kicker-line" />AI-ASSISTED CODE REVIEW</div><h1>Ship with more<br /><span>confidence.</span></h1><p className="hero-copy">PR Insight reads the actual changes in your pull request and surfaces the issues that matter—with evidence you can trust.</p><form className="submit-panel" onSubmit={handleSubmit}><label htmlFor="pr-url">GitHub pull request URL</label><div className="input-row"><div className="url-field"><span className="github-mark">⌘</span><input id="pr-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/org/repository/pull/123" disabled={isLoading} /></div><button type="submit" disabled={isLoading}>{isLoading ? <><span className="spinner" />Reviewing</> : <>Review PR <span>→</span></>}</button></div>{error && <div className="error-message" role="alert"><span>!</span>{error}</div>}<div className="form-hint"><span>◉</span> Public GitHub repositories only <span className="hint-divider" /> Read-only analysis</div></form><div className="empty-state"><div className="empty-icon"><span>✦</span></div><h2>Your review workspace is ready</h2><p>Paste a PR URL above to begin an evidence-backed review.</p><div className="empty-rule" /><div className="capabilities"><span>BUGS</span><i /><span>SECURITY</span><i /><span>MAINTAINABILITY</span><i /><span>TESTS</span></div></div></section> : <><div className="review-header"><div><div className="hero-kicker left-kicker"><span className="kicker-line" />REVIEW REPORT</div><h1>Change set <span>decoded.</span></h1></div><button className="secondary-button" onClick={reset}>← Review another PR</button></div><ReviewDashboard result={result} /></>}
      </main>
      <footer className="footer"><span>PR INSIGHT</span><span>Evidence first · decisions faster</span></footer>
    </div>
  );
}
