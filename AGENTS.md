# AGENTS.md — Siyaj

## Project
Siyaj is an Arabic-first AI security gateway that sits between users and LLMs.
It detects Saudi PII and prompt-injection (Arabic + English), reversibly pseudonymizes
sensitive values before they reach the LLM, enforces role-based policies, and produces
explainable, auditable decisions. A lightweight SOC layer turns events into alerts and incidents.

Portfolio project. Lab use only. Synthetic data only.

Before any task, read:
- docs/SPEC.md
- docs/architecture.md and docs/adr/
- the current task file in docs/tasks/

## Architecture (do not change without a new ADR)
- services/core — FastAPI modular monolith:
  api, normalizer, detectors, orchestrator, risk, policy, vault, proxy, output_scanner, audit
- services/ml_inference — ONNX Runtime model server (CAMeLBERT NER, Llama Prompt Guard 2). Internal HTTP only.
- services/analytics_worker — Redis Streams consumer: alerts, incidents, anomaly detection, KPIs.
- PostgreSQL 16, Redis 7, Prometheus + Grafana, Docker Compose.
- Event publishing uses the outbox pattern (write to PostgreSQL in the same transaction, then publish).

## Stack
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, asyncpg, redis-py, httpx,
cryptography, argon2-cffi, pytest, hypothesis, ruff, mypy.
Do NOT add any dependency not listed here without asking first.

## Commands
- `make up` / `make down` — start / stop the stack
- `make test` — run all tests
- `make lint` — ruff + mypy
- `make security` — semgrep, bandit, pip-audit, gitleaks
If a target does not exist yet, create it in the scaffold task.

## Hard rules (security) — never violate
1. Never log, print, store, or return raw prompt text or raw PII values outside the vault.
   Store HMAC fingerprints, entity types, offsets, and redacted text only.
2. Fail closed. If a detector or the ML service fails, apply the stricter policy and set
   `degraded_mode`. Never allow by default.
3. Never weaken, skip, or delete a security check, test, or lint rule to make something pass.
   If a test fails, fix the code or stop and report.
4. No secrets in code, tests, or fixtures. Use environment variables / Docker secrets.
   All test data must be synthetic.
5. Every endpoint enforces authentication + RBAC. Object access is filtered by tenant/owner
   in the repository layer (prevent BOLA/BFLA).
6. Use only vetted crypto from the `cryptography` library: AES-256-GCM, HMAC-SHA256, Argon2id.
   No custom crypto, no ECB, never reuse a nonce.
7. Never call real external services or networks in tests or demos. The upstream LLM is a mock in the lab.
8. Errors use RFC 7807 (problem+json) with a `correlation_id`. Never leak stack traces to clients.

## Human-owned modules
The project owner writes these personally. Do NOT implement or rewrite them unless the task
explicitly says so. You may write tests for them and review them.
- services/core/siyaj/detectors/saudi_ids.py
- services/core/siyaj/risk/scorer.py
- services/core/siyaj/vault/crypto.py
- services/core/siyaj/audit/chain.py

## Workflow
- One task = one branch = one small PR. Stay strictly inside the task's scope.
- If the spec is unclear or conflicts with this file, stop and ask. Do not guess.
- Every change ships with tests. Do not let coverage drop.
- Comments explain *why*, not *what*.
- PR description must include: what changed, why, how it was tested, and anything you were unsure about.

## Out of scope for v1 (do not introduce)
Kafka, Go, Kubernetes, Elasticsearch, separate frontend frameworks (Next.js/React),
Llama Guard 4, SSO/OIDC, file/image scanning, full SOAR.
Dashboards are Grafana; the demo page is a minimal static page served by core.

## Definition of done
- `make lint`, `make test`, and `make security` pass
- The task's acceptance criteria are met
- Docs updated if behavior changed
