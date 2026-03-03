# ── Base image — Python 3.11 slim ───────────────────────────
FROM python:3.11-slim

# Required for Whisper audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ──────────────────────────────
COPY interview_platform/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir openai-whisper

# Pre-download Whisper base model at build time (avoids delay at runtime)
RUN python -c "import whisper; whisper.load_model('base')"

# ── Copy project files ───────────────────────────────────────
COPY interview_platform/ ./interview_platform/
COPY tts/ ./tts/

# ── HuggingFace Spaces uses port 7860 ───────────────────────
ENV PORT=7860
EXPOSE 7860

# ── Start Flask ──────────────────────────────────────────────
WORKDIR /app/interview_platform
CMD ["python", "app.py"]
