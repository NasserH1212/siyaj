# Siyaj — Product Specification (v1)

> Status: Draft v0.1 · Owner: Nasser Altamimi · Last updated: 2026-11-11
> Lab project. Synthetic data only. Not a certified product and not a compliance claim.

## 1. Problem

Employees paste customer data into AI assistants to work faster. Banning these tools does not work: people route around the ban, and the organization loses visibility. Siyaj lets people keep using AI while stopping sensitive data from leaving.

Three risks drive the design:

1. **Personal data leakage** to an external LLM provider: a national ID, iqama, IBAN, or phone number inside a prompt.
2. **Prompt injection**, direct and indirect. It is LLM01 in the OWASP Top 10 for LLM Applications 2025.
3. **No audit trail**: no reliable record of who sent what, and why it was allowed or blocked.

**Saudi context.** The Personal Data Protection Law (PDPL) has been in force since 14 September 2023 and fully enforced since 14 September 2024. NCA Data Cybersecurity Controls (DCC-1:2022) cover protecting data when it is shared with third parties.

**Example.** A customer-service employee pastes a complaint that contains a customer's name, national ID, phone number, and IBAN, and asks the assistant for a summary. All of it leaves the organization. The complaint also contains a copied line that says "ignore your previous instructions", which tries to hijack the model.

## 2. Solution overview

Siyaj is an OpenAI-compatible gateway (`/v1/chat/completions`) that sits between users and the LLM. For every request it:

1. Authenticates the caller and checks their role (RBAC).
2. Normalizes Arabic text and keeps an offset map back to the original.
3. Detects sensitive data and attacks: checksum validators for Saudi identifiers, Arabic NER for names, and a prompt-injection classifier.
4. Scores risk and applies a versioned YAML policy: **allow**, **redact**, or **block**.
5. Replaces each sensitive value with a stable token (for example `NID_1`) and stores the value encrypted in a vault for 24 hours.
6. Sends only tokens to the LLM (a mock in the lab), scans the output, and restores values only if the caller's role allows it.
7. Writes a hash-chained audit entry and a **decision receipt** that explains the top factors.

**Principles:** fail closed; no raw prompt or PII outside the vault; synthetic data only.

## 3. Users and roles

| Role | Can | Cannot |
|---|---|---|
| `agent` (employee) | Send requests; restore values their role allows | See other users' data or any audit data |
| `analyst` (SOC) | See alerts, incidents, and redacted text | See or restore any sensitive value |
| `admin` | Manage users, policies, and keys | Read raw prompts (they are never stored) |
| `auditor` | Read the audit log and verify chain integrity | Modify anything |

## 4. Must-have scope (v1, weeks 1–8)

| # | Item | Week | Done when |
|---|---|---|---|
| 1 | Auth (JWT + API keys) and RBAC with four roles | 2 | Every endpoint requires auth; BOLA/BFLA tests pass |
| 2 | Arabic normalization with an offset map | 3 | Offsets map back to the original text; invisible characters are removed and logged as an injection signal |
| 3 | Deterministic detectors: national ID/iqama, phone, IBAN, CR number, cards | 3 | Checksum-validated; unit and property tests pass |
| 4 | OpenAI-compatible proxy to a Mock LLM | 3 | `/v1/chat/completions` works end to end against the mock |
| 5 | Versioned YAML policy engine: allow, redact, block | 3 | The policy version is recorded with every decision |
| 6 | Reversible pseudonymization vault, output scanning, role-based restore | 4 | Analyst gets 403 on restore; nothing restores after expiry |
| 7 | Hash-chained audit log | 4 | Editing any row is detected |
| 8 | Arabic NER and injection detection in a separate ONNX service | 5 | If the ML service is down, the system keeps working in degraded mode with the stricter policy |
| 9 | Explainable risk score and decision receipt | 5 | Every decision has a receipt with its top factors |
| 10 | SynthSA synthetic dataset and evaluation report with ablation | 2–5 | Data regenerates reproducibly; the ablation table has measured numbers |
| 11 | Four Grafana dashboards | 6 | Dashboards load after `make up` with no manual setup |
| 12 | Security CI: Semgrep, Bandit, pip-audit, gitleaks, Trivy, OWASP ZAP | 1–7 | CI is green and catches a planted fake secret |

**Should (if time allows):** alerts become incidents mapped to MITRE ATLAS and ATT&CK; usage anomaly detection (Isolation Forest); Arabic incident summary from a fixed template; load test with Locust; backup restore drill.

**Could (weeks 9–12):** a light Arabic injection classifier if Prompt Guard 2 is weak on Arabic; an industrial policy pack (equipment tag IDs, OT addresses); PostgreSQL row-level security for tenants.

## 5. Won't build in v1

| Item | Why not |
|---|---|
| Kafka | Redis Streams is enough at lab scale |
| Go, Kubernetes, Elasticsearch | Operational weight with no value for the demo |
| Next.js or React UI | Grafana plus one minimal static demo page served by core |
| Llama Guard 4 | Too heavy for CPU-only inference; Prompt Guard 2 covers injection |
| SSO / OIDC | JWT and API keys are enough for the lab |
| File and image scanning | v1 handles text only |
| Full SOAR | v1 stops at alerts and incidents |
| Training a model from scratch | Pretrained models, fine-tuned where needed |

## 6. Demo scenario (5 minutes)

One story: an employee uses AI safely, an attacker tries to exploit it, and Siyaj detects, responds, and proves it with numbers.

| Time | Scene | What the viewer sees |
|---|---|---|
| 0:00–0:40 | Problem | Data gets pasted into AI tools, PDPL applies, and bans get bypassed |
| 0:40–1:20 | Architecture | The model only ever sees tokens |
| 1:20–2:10 | Event 1 | A request with an ID, an IBAN, and a name reaches the model as tokens; the reply is still useful; an analyst account cannot restore the values |
| 2:10–2:50 | Event 2 | An indirect Arabic injection hidden in copied text is isolated; the decision receipt shows why |
| 2:50–3:30 | Response | Gradual leakage triggers alerts, then an incident with an Arabic summary, then the key is suspended (lab only) |
| 3:30–4:15 | Dashboards | Data Protection and SOC dashboards in Grafana |
| 4:15–5:00 | Numbers | Ablation table, leakage rate, added latency, and what did not work and the plan for it |

## 7. Success metrics (targets, not results)

| Metric | Target | How it is measured |
|---|---|---|
| Leakage rate, deterministic types | 0% | 1,000 requests containing canary values |
| F1, deterministic types | ≥ 0.98 | Span level |
| F1, person names | ≥ 0.85 | Frozen test set |
| Recall, Arabic injection | ≥ 0.80 at FPR ≤ 2% | Arabic injection set |
| Added latency (p95) | ≤ 150 ms on CPU | Locust with a fixed-latency Mock LLM |

Results are reported as an ablation (rules only → plus NER → full system) and published as measured, even when they miss the target.

## 8. Constraints and assumptions

- Synthetic data only. No real PII in code, tests, fixtures, or demos.
- Lab only. The upstream LLM is a mock, and tests and demos never call real external services.
- One developer, about 15–20 hours a week, 8 weeks to v1.0.0 (target: 9 January 2027).
- Development runs in GitHub Codespaces (2 cores, 8 GB RAM). Inference is CPU-only.
- Claude Code and Codex implement tasks under `AGENTS.md`; the owner reviews every PR. Four modules are written by the owner: `detectors/saudi_ids.py`, `risk/scorer.py`, `vault/crypto.py`, `audit/chain.py`.
- Models: Llama Prompt Guard 2 (86M), under the Llama 4 Community License ("Built with Llama" is required in the README), and CAMeLBERT MSA NER.
- Datasets: Wojood (CC-BY-4.0), ANERcorp, deepset/prompt-injections, plus the SynthSA set this project generates.

## 9. Open questions

- Is Prompt Guard 2 accurate enough on Arabic injection? If not, compare it with a light Arabic classifier in weeks 9–12.
- Does CAMeLBERT NER need fine-tuning on Wojood to reach F1 0.85 on names?
- Can added latency stay at or below 150 ms p95 on 2 CPU cores with both models loaded? INT8 quantization is the fallback to test.
- Confirm the unified CR number format (10 digits starting with 7) against the official source before implementing the detector.
- Official COOP duration and exam weeks are pending from the training coordinator; they may shift the timeline.
