CORE := services/core

.PHONY: up down test lint security

# .env is created from the example on first run so `make up` works in a fresh Codespace.
up:
	@test -f .env || cp .env.example .env
	docker compose up -d --build --wait

down:
	docker compose down

test:
	cd $(CORE) && python -m pytest

lint:
	cd $(CORE) && ruff check . && ruff format --check . && mypy

security:
	@echo "added in Task 1.2"
