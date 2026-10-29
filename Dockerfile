FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY .streamlit ./.streamlit
RUN pip install --no-cache-dir -e ".[dev,piper,gui]"
COPY tests ./tests
ENV EVERGREEN_PROJECTS_DIR=/data/projects PYTHONUTF8=1
CMD ["evergreen", "--help"]
