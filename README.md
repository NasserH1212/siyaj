# siyaj
Arabic-first AI security gateway: detects Saudi PII and prompt injection, pseudonymizes sensitive data before it reaches LLMs, with auditable policy decisions.

## Quickstart

1. Open the repository in GitHub Codespaces (the dev container includes Docker).
2. Start the stack (creates `.env` from `.env.example` on first run):
   ```sh
   make up
   ```
3. Check health:
   ```sh
   curl localhost:8000/health
   # {"status":"ok","db":"ok","redis":"ok"}
   ```

For lint and tests: `pip install -e "services/core[dev]"`, then `make lint` and `make test`. Stop with `make down`.
