# PR Insight Development Plan

This plan is ordered so that each milestone produces a testable result. We will not implement the whole application in one step. After each milestone, we will review what was learned and decide whether the next step is still justified.

## Milestone 0 — documentation and decisions

Status: proposed.

Deliverables:

- Approved architecture and folder structure.
- Agreed Python and Node versions.
- Decision on whether the initial API supports only public pull requests.
- A small definition of a valid structured finding.
- Agreed tool-call and iteration budgets for the bounded agent.

Acceptance criteria: the user approves [README.md](./README.md), [PLAN.md](./PLAN.md), and [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md), or requests changes.

## Milestone 1 — backend skeleton and health endpoint

Create the Python package, FastAPI application, configuration loading, structured logging, and a health endpoint. Add pytest setup and a test that starts the application without external credentials.

Why first: it verifies the development environment and establishes the application boundary before GitHub or AI complexity is introduced.

Acceptance criteria:

- FastAPI starts locally.
- Configuration comes from environment variables with safe validation.
- Health endpoint and basic error handling are tested.
- No API key is hardcoded.

## Milestone 2 — GitHub pull request ingestion

Implement URL parsing and a GitHub REST client behind a service interface. Fetch metadata, changed files, patches, and commits as needed. Use mocked HTTP tests for deterministic behavior and a small, manually run smoke test against the selected public repository.

Acceptance criteria:

- A valid public PR URL is parsed correctly.
- Invalid hosts, repositories, and PR numbers are rejected clearly.
- File status, path, additions/deletions, patch, and line metadata are normalized.
- Missing patches, binary files, renames, deletions, pagination, rate limits, and oversized diffs are handled explicitly.

## Milestone 3 — review domain model and deterministic validation

Define Pydantic schemas for review requests, review status, findings, evidence, and responses. Implement validation rules for severity, category, confidence, file path, and line references. Add a deterministic review result fixture for tests; it is a test fixture, not the product demonstration.

Acceptance criteria:

- Invalid finding output cannot pass schema validation.
- Line references cannot point outside the supplied diff without an explicit unavailable state.
- Speculative findings can be represented without being presented as confirmed defects.

## Milestone 4 — replaceable LLM service

This milestone is the bounded LangChain tool-calling review workflow.

Implement an LLM provider protocol and a Groq adapter. Add a small LangChain tool-calling workflow with only these read-only tools: `fetch_pr_metadata`, `fetch_changed_files`, `inspect_file_diff`, and `generate_test_suggestions`. The model may choose tools based on the PR and changed files, but a controller enforces maximum tool calls and maximum iterations.

Tools may call the GitHub service and deterministic review utilities, but may not execute repository code, modify files, merge pull requests, or post GitHub comments. The final structured response must pass Pydantic validation and diff-evidence checks.

Acceptance criteria:

- The review service depends on an interface, not directly on Groq SDK details.
- The review service depends on a provider abstraction and LangChain orchestration, not Groq SDK details.
- The model can select only the four allowlisted read-only tools.
- Tool arguments and outputs are schema-validated.
- The loop stops at hard call and iteration limits and records the stopping reason.
- Provider errors, malformed responses, timeouts, and token/input limits are handled.
- Prompt instructions prohibit invented evidence and line references.
- Tests use a fake provider; one live call is a documented manual smoke test.

## Milestone 5 — review API and SQLite persistence

Add SQLAlchemy models/repositories for review requests, normalized PR metadata, and findings. Implement an endpoint to start a review and an endpoint to retrieve its status/result. For the initial MVP, the request may be synchronous if practical; asynchronous job processing will be considered only if latency requires it.

Acceptance criteria:

- A review can be created, persisted, retrieved, and represented as failed with an actionable error.
- External calls are not repeated accidentally on a simple result read.
- Database behavior is covered with isolated tests.

## Milestone 6 — React dashboard

Create the frontend shell, PR URL form, loading/error states, summary, severity/category filters, finding cards, evidence blocks, and line references. The UI must communicate uncertainty and unavailable references clearly.

Acceptance criteria:

- A user can submit a URL and view a real review response.
- The UI remains usable for no findings, many findings, long evidence, and partial failures.
- No secret is sent to or stored in the frontend.

## Milestone 7 — integration, hardening, and evaluation harness

Add API integration tests using mocked GitHub and LLM boundaries, an optional live smoke test, request correlation IDs, metrics/logging useful for debugging, and a repeatable evaluation document. Use actual public pull requests, beginning with `EricCogen/GauntletCI-Demo`, then selected PRs from FastAPI, Django, or Spring Boot.

Evaluation should record the PR URL, commit state, model/configuration, prompt version, expected evidence, observed findings, false positives, false negatives, and reviewer notes. We will not publish an accuracy percentage unless the set and rubric justify it.

## Future milestones, only when justified

- Static analysis adapters such as Ruff, Semgrep, or language-specific tools.
- Repository context retrieval for cases where a diff alone is insufficient.
- Generated test suggestions and test-quality checks.
- GitHub webhook-triggered reviews.
- Human-approved GitHub review comments.
- Review history, analytics, and provider/model comparison.
- Additional LLM providers.

## Initial dependencies

Backend runtime dependencies are expected to include FastAPI, Uvicorn, Pydantic settings support, an HTTP client such as httpx, SQLAlchemy, LangChain core/tooling packages, and the Groq integration package or a small provider adapter. Development dependencies are expected to include pytest, pytest-asyncio if needed, and a mocking tool such as respx if the HTTP client requires it.

Frontend dependencies are expected to include React, TypeScript, a Vite-based toolchain, Tailwind CSS, and a small HTTP client or the browser fetch API. We should avoid adding a UI component framework until the dashboard needs one.

Exact versions will be pinned during Milestone 1 after checking the available runtime and current compatibility. Dependency additions that materially increase complexity will be discussed first.

## Main risks and mitigations

| Risk | Mitigation |
| --- | --- |
| GitHub rate limits or transient failures | Optional token, timeouts, bounded retries, clear status, and cached persisted results |
| Large or binary diffs | Size limits, truncation metadata, explicit unsupported-file handling, and no pretend analysis |
| LLM hallucinated lines or findings | Diff-derived line mapping, strict schemas, evidence requirements, and uncertainty labels |
| Prompt injection in source code or PR text | Treat repository content as untrusted input; delimit it and instruct the model not to follow embedded instructions |
| Agent overreach or runaway tool use | Allowlist four read-only tools, validate arguments/results, enforce maximum calls and iterations, and reject side effects |
| Non-deterministic output | Low-temperature/provider configuration where available, schema validation, stored prompt/model metadata, and evaluation snapshots |
| False positives reducing trust | Conservative severity, evidence display, confidence calibration, and human verification |
| Secrets exposed in logs or browser | Backend-only secrets, redaction, and tests for configuration behavior |
| Slow synchronous reviews | Measure first; introduce a job/status mechanism only when latency or timeout evidence warrants it |

## Definition of done for the initial MVP

A developer can submit a real public GitHub pull request URL, see retrieved PR metadata and changed files, receive a validated structured AI review, inspect evidence and line references, and understand which findings are uncertain. The behavior is covered by automated tests at the service/API boundaries and documented live smoke/evaluation runs. Known limitations are visible rather than hidden.
