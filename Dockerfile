FROM python:3.15-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY .streamlit ./.streamlit
RUN pip install --no-cache-dir -e ".[dev,piper,gui]"
COPY tests ./tests
ENV EVERGREEN_PROJECTS_DIR=/data/projects PYTHONUTF8=1
# Default = the GUI, listening on $PORT (Render injects it; 8501 locally). Commands passed to
# `docker compose run app ...` (evergreen, pytest, bash) replace this CMD, so the CLI flow is unchanged.
CMD ["sh", "-c", "exec streamlit run src/evergreen/gui/app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]
