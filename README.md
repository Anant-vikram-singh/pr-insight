# PR Insight

PR Insight is an AI-assisted pull request reviewer for public GitHub pull requests. A user submits a pull request URL, and a bounded LangChain tool-calling workflow retrieves the real pull request metadata, changed files, and unified diffs before an LLM produces evidence-backed review findings. A React dashboard presents the results in a form useful to a developer.

This project is intentionally incremental. The first version is a modular monolith with one bounded tool-calling agent, rather than a set of services or multiple agents. This demonstrates genuine agent behavior while keeping the workflow understandable and interview-defensible.

## Current status

The current MVP includes the FastAPI/GitHub integration, bounded LangChain tool-calling review engine, Groq provider integration, and React/TypeScript/Tailwind dashboard. The frontend connects to the real FastAPI review endpoint and does not use mock review data.

Review history persistence, webhooks, repository-wide context, automated GitHub comments, and deployment are not implemented yet.

## Product goals

- Analyze actual public GitHub pull requests, not fabricated examples.
- Return structured findings with file paths, line references when available, severity, category, explanation, evidence, suggested fixes, and calibrated confidence.
- Clearly distinguish evidence-backed findings from speculative suggestions.
- Make provider-specific LLM code replaceable.
- Make every important result traceable to GitHub data and the review prompt/response.
- Keep the code simple enough to explain and defend in a technical interview.

## Technology stack

| Area | Initial choice | Reason |
| --- | --- | --- |
| Frontend | React, TypeScript, Tailwind CSS | Component-based dashboard with a small, maintainable UI layer |
| Backend | Python, FastAPI, Pydantic | Typed HTTP API, validation, and good developer ergonomics |
| AI orchestration | LangChain tool-calling agent with a bounded loop | Lets the model choose read-only tools while keeping execution controlled |
| AI provider | Groq API with `openai/gpt-oss-20b` by default | Fast tool-capable reasoning; hidden behind a provider abstraction |
| Git hosting | GitHub REST API | Official source for pull request metadata and diffs |
| Persistence | None in the current MVP | Review history can be added later without changing the review API boundary |
| Testing | Pytest, FastAPI test client, mocked integration boundaries | Fast deterministic tests plus selected live evaluations |

## How the planned workflow works

1. The user pastes a public pull request URL into the frontend.
2. The frontend sends the URL to the FastAPI backend.
3. The backend parses and validates the owner, repository, and pull request number. It does not trust arbitrary URLs or accept secrets from the browser.
4. The review service creates a bounded LangChain tool-calling workflow. The model can choose among `fetch_pr_metadata`, `fetch_changed_files`, `inspect_file_diff`, and `generate_test_suggestions`.
5. Each tool validates its arguments, calls the GitHub service or deterministic review logic, validates its output, and returns bounded data.
6. A controller limits total tool calls and agent iterations. The workflow stops on a final answer, a limit, a provider error, or invalid tool behavior.
7. The agent cannot execute repository code, modify files, merge pull requests, or post GitHub comments. GitHub access remains behind the GitHub service, and LLM access remains behind the provider abstraction.
8. The final response is parsed and validated with Pydantic, then checked against the diff evidence map.
9. The FastAPI endpoint returns the validated review result directly; the current MVP does not persist review history.
10. The frontend displays the result. Evaluation compares findings with the actual PR diff and, where available, human review discussion.

## Normal LLM call versus tool-calling workflow

A normal LLM call sends a prompt and context to a model and receives text or structured data in one response. The application decides all data retrieval before that call. The model cannot request a specific missing piece of PR context.

In PR Insight, the model receives a prompt plus a small declared tool catalogue. It can request a tool such as `inspect_file_diff` with validated arguments. The application executes that read-only tool, puts the validated result back into the conversation, and lets the model continue until it produces a final structured review. The model chooses among information-gathering actions, but the application controls what actions exist, validates every input and output, and enforces hard call and iteration limits. This is bounded agentic behavior, not an autonomous coding agent.

## Important safety and quality rules

- API keys are loaded from environment variables and never committed.
- GitHub and LLM calls have timeouts, useful error messages, and bounded input sizes.
- A line reference is shown only when it is present in the diff or can be deterministically mapped. The model must not invent one.
- A possible issue is labelled as a suggestion or speculative concern when the diff does not establish it.
- LLM output is treated as untrusted data and validated before persistence or display.
- Tool calls are read-only and run only through allowlisted LangChain tools.
- Tool arguments, tool results, and final findings are validated with typed schemas.
- The tool-calling loop has hard maximum call and iteration limits.
- Accuracy percentages will not be claimed without a documented evaluation set, rubric, and repeatable procedure.
- The application is an assistant, not an automatic merge gate. Developers remain responsible for verifying findings.

## Backend setup

The backend requires Python 3.11 or newer within the tested range.

From the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\\backend[dev]"
Copy-Item .\\backend\\.env.example .\\backend\\.env
```

Edit `backend/.env` and set `GROQ_API_KEY` for AI reviews. `GITHUB_TOKEN` is optional for public pull requests, but can increase GitHub API rate limits. Never commit either local `.env` file.

Run the backend from the `backend` directory:

```powershell
cd .\\backend
python -m uvicorn app.main:app --reload
```

The health check is available at `http://127.0.0.1:8000/health`.

Run the full test suite with:

```powershell
cd .\\backend
python -m pytest
```

The normal test suite uses mocked GitHub and LLM boundaries and does not require a Groq key. The optional live smoke test makes a real Groq request only when explicitly enabled.

## Frontend setup

The frontend uses Vite for local development. Its default `/api` base URL is proxied to the backend at `http://127.0.0.1:8000`, so no backend CORS change is needed for local development.

In a second PowerShell terminal, from the repository root:

```powershell
cd .\frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open `http://127.0.0.1:5173`. For a different deployment URL, set `VITE_API_BASE_URL` to the backend API base, such as `https://api.example.com/api`.

Create a production bundle with:

```powershell
cd .\frontend
npm run build
```

## Test with a real public pull request

The API uses GitHub's public REST API. An unauthenticated request is enough for a small smoke test, but `GITHUB_TOKEN` can be added to `backend/.env` for a higher rate limit. Do not commit that file.

With the backend running, submit a public pull request:

```powershell
$body = @{ url = "https://github.com/EricCogen/GauntletCI-Demo/pull/1" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/github/pull-request/inspect -ContentType "application/json" -Body $body
```

Replace `/pull/1` with an existing public pull request number if that example is no longer available. The response contains normalized metadata, changed files, patches when GitHub provides them, and a `files_truncated` flag when configured bounds are reached.

## AI review engine

Sprint 2 adds `POST /api/reviews`. The endpoint runs one LangChain tool-calling agent using the configured Groq model. The model can choose among four read-only tools: `fetch_pr_metadata`, `fetch_changed_files`, `inspect_file_diff`, and `generate_test_suggestions`.

The application owns the execution loop. It validates tool arguments and results, allows at most 12 tool calls and 8 model iterations, and validates the final JSON response with Pydantic. File paths and line ranges are checked against the actual GitHub diff. Source code and PR descriptions are treated as untrusted content; the agent cannot execute code, modify files, merge pull requests, or post comments.

The normal test suite does not require a Groq key. To run the optional live provider smoke test:

```powershell
$env:RUN_LIVE_GROQ = "1"
$env:GROQ_API_KEY = "your-key"
cd .\\backend
python -m pytest tests/integration/test_live_groq.py -v
```

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Backend health check |
| POST | `/api/github/pull-request/inspect` | Fetch normalized GitHub PR metadata, changed files, and patches |
| POST | `/api/reviews` | Run the bounded AI review workflow |

Review request body:

```json
{"url": "https://github.com/owner/repository/pull/123"}
```

The review endpoint returns the request URL, structured review findings, status, tool-call count, iteration count, and stop reason.

## Documentation

- [PLAN.md](./PLAN.md) contains the milestone roadmap and acceptance criteria.
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) explains the system design, boundaries, data flow, and extension points.

## Deliberate non-goals for the MVP

The first version will not include LangGraph, multi-agent architecture, vector databases, repository-wide RAG, microservices, automatic GitHub comments, webhooks, automatic code changes, repository code execution, or merge operations.
