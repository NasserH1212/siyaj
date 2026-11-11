FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 siyaj \
    && useradd --system --uid 10001 --gid siyaj --no-create-home --shell /usr/sbin/nologin siyaj

WORKDIR /app
COPY pyproject.toml ./
COPY siyaj ./siyaj
RUN pip install .

USER siyaj
EXPOSE 8000

# slim has no curl; use the interpreter that's already there.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# Access logs are off: request lines include query strings, which could carry prompt text
# or PII (AGENTS.md rule 1). tests/test_runtime_config.py guards this flag.
CMD ["uvicorn", "siyaj.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-access-log"]
