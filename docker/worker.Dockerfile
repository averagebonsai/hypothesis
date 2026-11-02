# Trusted dependencies/framework only. Experimental code is never part of this build.
FROM ghcr.io/astral-sh/uv:0.13.6-python3.13-trixie-slim
WORKDIR /opt/toolkit
ENV UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/opt/toolkit/src:/bundle" \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/cache \
    MPLCONFIGDIR=/tmp/matplotlib \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY src ./src
RUN uv sync --locked --no-editable
COPY tests ./tests
COPY docker ./docker
COPY prompts/blind_coding_agent.md ./prompts/blind_coding_agent.md
ENV PATH="/opt/toolkit/.venv/bin:$PATH"
USER 10001:10001
WORKDIR /tmp
ENTRYPOINT ["python", "-m", "extension_worker"]
