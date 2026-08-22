# ARCH BRAIN STORMING — cloud image (Hugging Face Space / any Docker host)
# Python server + Claude Code CLI, so AI Read works with the PC switched off.
FROM python:3.12-slim

# node 20 for the Claude Code CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# python deps
RUN pip install --no-cache-dir \
        bottle waitress ezdxf shapely pillow matplotlib pdfplumber pymupdf

# HF Spaces runs as uid 1000; give it a home + the app
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    CLAUDE_BIN=/usr/bin/claude \
    DATA_DIR=/data \
    PORT=7860 \
    MPLBACKEND=Agg

WORKDIR /app
COPY --chown=user . /app

# the CLI must skip its first-run wizard when driven headless
RUN mkdir -p /home/user/.claude \
    && echo '{"hasCompletedOnboarding": true}' > /home/user/.claude.json

EXPOSE 7860
CMD ["python", "webserver.py"]
