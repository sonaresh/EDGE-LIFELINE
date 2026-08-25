# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG BUILD_REVISION=unversioned
ARG BUILD_TIMESTAMP=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EDGE_LIFELINE_BUILD_REVISION=${BUILD_REVISION} \
    EDGE_LIFELINE_BUILD_TIMESTAMP=${BUILD_TIMESTAMP}

RUN groupadd --gid 10001 edge && useradd --uid 10001 --gid edge --no-create-home --shell /usr/sbin/nologin edge
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir uv==0.11.33 \
    && uv sync --frozen --no-dev --no-editable \
    && rm -rf /root/.cache/uv

ENV PATH="/app/.venv/bin:${PATH}"

USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2).read()"]

CMD ["uvicorn", "edge_lifeline.foundation.app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
