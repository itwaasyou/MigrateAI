# Product status and next steps

## Implemented

- Next.js dashboard, email/password accounts, revocable HttpOnly sessions, workspace membership roles, and tenant-scoped endpoints.
- Safe ZIP ingestion and asynchronous in-process analysis, with SQLite by default and configurable PostgreSQL support.
- Deterministic source/manifest scanning, file inventory and hashes, import edges, database/API signals, risk factors, and evidence records.
- Gemini-backed repository chat, bounded lexical retrieval, persisted chat, and citation-reference validation.
- Impact estimate, persisted phased migration plan with a highlighted next action, a plain-language reason and completion check per task, task status updates, and Markdown export.
- Synthetic legacy monolith demo, API workflow tests, Ruff checks, frontend typecheck/build, and CI.

## Not implemented yet

1. GitHub OAuth, repository/branch picker, commit history, and pull request metadata.
2. Email verification and password reset delivery.
3. Tree-sitter plugins and accurate AST analysis across every requested language; the current scanners combine Python AST with deterministic manifest/text signals.
4. Incremental parsing/embedding cache, vector retrieval, and background AI workflows.
5. Full architecture and dependency graph visualizations, source explorer, and clickable source viewer.
6. Target-aware task dependencies and work estimates, plus a more complete migration simulation.
7. Broader synthetic evaluation repositories, evidence/plan metrics, and Playwright end-to-end coverage.
8. Cloud deployment-specific secret management, monitoring integrations, and production security review.

The current what-if endpoint reports the measured files and modules touched by detected database/API signals. It does not transform code or claim to predict every downstream change.
