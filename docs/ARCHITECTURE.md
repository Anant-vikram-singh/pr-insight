# PR Insight Architecture

## Design choice

PR Insight will start as a modular monolith: one backend deployment with internal modules and one frontend application. A modular monolith gives us clear boundaries without the operational cost of microservices. The modules can later be extracted or extended if measurements show that they need independent scaling or deployment.

The backend will use dependency inversion at the two unstable boundaries: GitHub access and LLM access. Application code will depend on small interfaces, while GitHub REST and Groq are adapters. LangChain provides tool-calling orchestration, but receives only explicitly allowlisted tools and does not own GitHub credentials or direct HTTP access.

## Initial folder structure

```text
PR Insight/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application composition
│   │   ├── api/                    # HTTP routes and request/response wiring
│   │   ├── core/                   # settings, logging, errors, shared policies
│   │   ├── models/                 # SQLAlchemy persistence models
│   │   ├── schemas/                # Pydantic API and domain schemas
│   │   └── services/               # GitHub, review orchestration, LLM adapters
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/             # reusable UI pieces
│   │   ├── pages/                  # screen-level views
│   │   ├── services/               # backend API client
│   │   ├── types/                  # frontend response types
│   │   └── App.tsx
│   ├── package.json
│   └── .env.example
├── docs/
│   ├── ARCHITECTURE.md
│   └── evaluations/                # later: reproducible review evaluations
├── README.md
└── PLAN.md
```

The exact module names may be refined during implementation, but the responsibility boundaries should remain stable.

The `tools/` package contains only the four allowlisted read-only LangChain tools. It is separate from `services/` so tool schemas and safety rules remain visible without giving the agent direct access to provider or HTTP implementation details.

## Component responsibilities

### API layer

The API layer exposes a small public contract, initially something similar to `POST /api/reviews` and `GET /api/reviews/{review_id}`. It validates input, calls the review application service, converts domain results into response schemas, and maps known failures to safe HTTP errors. It should not contain GitHub URL parsing logic, prompt construction, or database queries directly.

### Review application service

This is the use-case coordinator. It receives a pull request URL, creates the bounded LangChain tool-calling workflow, supplies initial context, validates tool interactions and the final result, persists the review, and returns the result. It owns workflow order, budgets, and status transitions, not provider-specific details.

### GitHub service

The GitHub adapter parses supported public GitHub URLs and calls the REST API. It translates GitHub responses into internal models such as pull request metadata and changed file. It owns HTTP timeouts, authentication headers, pagination, rate-limit interpretation, and GitHub-specific errors.

The adapter must preserve enough source information to explain what was analyzed: repository, PR number, head/base commit identifiers, file status, old/new paths, patch, and API retrieval timestamp.

### Diff normalizer and evidence mapper

The normalizer converts patches into bounded review input and identifies which new-file lines are actually present in the patch. This is important because an LLM can suggest a plausible line number that is not in the changed code. The backend should validate any model-reported location against this mapping and use an explicit unavailable value when exact mapping is not possible.

### LLM service

The review service depends on an interface such as an `LLMProvider` concept rather than on Groq directly. The Groq adapter handles authentication, model selection, request formatting, timeouts, and provider errors. The prompt includes a structured review contract and clearly delimited untrusted code. The model output is parsed as data, validated with Pydantic, and then checked against the available diff evidence.

The first AI workflow is one bounded tool-calling agent. It is not a multi-agent system. If later testing shows that large pull requests need chunking or an aggregation pass, that can be added inside the review service without changing the API or persistence contract.

### Tool-calling agent and allowlisted tools

LangChain supplies the model with four tools. These tools are typed application functions, not arbitrary Python execution:

- `fetch_pr_metadata`: retrieves normalized title, description, state, author, base/head commits, and repository identity through the GitHub service.
- `fetch_changed_files`: retrieves a bounded list of changed-file summaries and patch availability through the GitHub service.
- `inspect_file_diff`: accepts a validated changed-file path and returns bounded patch context plus the backend-generated changed-line map for that file.
- `generate_test_suggestions`: accepts validated review context and produces structured test ideas tied to changed behavior. It does not write or run tests.

The model may choose which tools to invoke and in what order. The tool implementation, not the model, decides how a request reaches GitHub or deterministic review logic.

The controller validates tool names and arguments, executes only allowlisted read-only tools, validates and size-limits each result, and continues until a final answer or a hard maximum tool-call or iteration count is reached. The final answer is validated with Pydantic and evidence checks. If the budget is exhausted, the system returns a partial/limited review status rather than pretending the analysis is complete.

The initial budgets will be configuration values with conservative defaults, for example a maximum of 12 tool calls and 8 model iterations. The exact values will be measured and documented during implementation. The controller counts both calls and iterations to prevent runaway behavior.

The agent cannot execute repository code, run shell commands, modify files, merge pull requests, or post GitHub comments. No side-effecting tool will be registered.

### Persistence layer

SQLite stores review request identity, source PR metadata, status, model/prompt metadata, timestamps, and normalized findings. Repositories keep SQLAlchemy details out of the application service. SQLite is sufficient for local MVP use; a later PostgreSQL migration should be possible because the domain model is not tied to SQLite-specific behavior.

### Frontend

The React app owns user interaction and presentation. It submits only the public PR URL, reads review status as designed, and renders validated backend data. It does not call GitHub, LangChain, or Groq directly and never receives provider secrets.

## End-to-end data flow

The review application service invokes a LangChain agent configured with the four allowlisted tools. Tool requests flow through the GitHub service or deterministic review utilities; they never bypass those boundaries.

```text
Browser
  │ PR URL
  ▼
FastAPI route
  │ validated request
  ▼
Review application service
  ├── GitHub adapter ──► GitHub REST API
  │       │ metadata + changed files + patches
  │       ▼
  │   normalized diff/evidence map
  │
  ├── LLM provider adapter ──► Groq/Llama
  │       │ structured candidate findings
  │       ▼
  │   Pydantic + evidence validation
  │
  └── repository ──► SQLite
          │ validated review result
          ▼
       FastAPI response ──► React dashboard
```

## Review finding contract

Each finding should contain:

- `file_path`: changed file path, or an explicit non-file scope for a general observation.
- `line_start` and optional `line_end`: only when the location is available and verified against the diff.
- `severity`: `critical`, `high`, `medium`, or `low`.
- `category`: for example `bug`, `security`, `performance`, `maintainability`, `testing`, or `style`.
- `title` and `explanation`.
- `evidence`: a short excerpt or exact diff context supporting the claim.
- `suggested_fix`.
- `confidence`: a bounded value only when the calibration meaning is documented.
- `status` or `certainty`: enough information to distinguish evidence-backed findings from speculative suggestions.

The model is not the source of truth for file locations. The supplied diff and backend evidence map are the source of truth. A finding that cannot be tied to supplied evidence should be rejected, downgraded to a clearly marked suggestion, or omitted. The same Pydantic validation boundary applies to tool arguments, tool outputs, test suggestions, and final findings.

## Normal LLM call versus tool-calling workflow

A normal LLM call is a single request/response: the application gathers all context, sends a prompt, and receives text or structured output. The model cannot ask the application for another file or decide that metadata is needed.

The PR Insight workflow gives the model a declared set of tools and lets it request read-only information during a bounded conversation. LangChain formats tool definitions and messages, while our controller decides whether a requested call is allowed, validates its arguments, invokes the application tool, validates the output, and enforces call/iteration budgets. The model has limited decision-making over information gathering, but it has no authority to perform side effects. The final response is untrusted data and must pass Pydantic and evidence validation.

## GitHub REST endpoints

The initial integration will use these official endpoints:

1. `GET /repos/{owner}/{repo}/pulls/{pull_number}` — pull request metadata, base/head references, title, body, state, and commit identifiers.
2. `GET /repos/{owner}/{repo}/pulls/{pull_number}/files` — changed file paths, status, additions/deletions, patch text, and pagination.
3. `GET /repos/{owner}/{repo}/pulls/{pull_number}/commits` — commits in the pull request when commit-level context is useful.
4. `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` — later evaluation/supporting review evidence; not required for the first generated review.
5. `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments` — later evaluation of inline discussion; not required for the first generated review.

The implementation must honor GitHub API version headers, pagination, response limits, authentication configuration, rate-limit responses, and the distinction between a missing patch and an empty patch.

## Error handling and observability

Expected failures should become structured application errors: invalid URL, PR not found, access/rate limit, unsupported or oversized diff, provider timeout, provider refusal, malformed model output, and persistence failure. Logs should include a correlation/review ID and operation names, but must redact API keys, authorization headers, and unnecessarily large source contents.

The system should store enough metadata to reproduce a result conceptually: source PR and commit IDs, retrieval time, prompt/schema version, provider/model name, and review status. Storing full prompts or diffs requires a deliberate privacy/retention decision; the MVP should avoid logging them by default.

## Security and trust boundaries

- User input, PR descriptions, file names, and source code are untrusted.
- Repository content must be delimited in prompts and must never override system review instructions.
- Only the backend holds GitHub and Groq credentials.
- Public PR content may contain secrets; logs and persisted data should minimize accidental duplication.
- LLM findings are recommendations, not authorization to merge code or run commands.
- No code from a PR is executed by the MVP.

## Future extension points

The service boundary can later expose adapters for static analyzers. The normalized changed-file model can later be enriched with repository context or retrieval results. The provider protocol can support another LLM without changing the review API. Webhook handling can invoke the same review application service as the manual URL route. A future GitHub comment feature should require explicit developer approval and use the persisted evidence rather than posting raw model output blindly.

## Known limitations

Diff-only review cannot reliably reason about unchanged callers, runtime configuration, generated code, cross-file invariants, or repository-wide security policies. LLM output can still be wrong even when it cites real lines. Large, binary, renamed, or generated files may need special handling. GitHub rate limits and Groq availability affect live behavior. These limitations are part of the product contract and must be represented in the UI and evaluation notes.
