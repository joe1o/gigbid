# Dockerfile - one image that runs all of GigBid (used by Hugging Face Spaces / Render).
# Stage 1 builds the React app; stage 2 is the Python app that serves it.

# ---- stage 1: web app ----
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npx vite build

# ---- stage 2: Python services ----
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=7860 HF_HUB_DISABLE_SYMLINKS_WARNING=1
COPY . .
COPY --from=web /web/dist apps/web/dist
RUN pip install --no-cache-dir -e .
# Download the two open models into the image now, so the first request is not slow.
RUN python -c "from rag import models; models.embed_query('warm up'); models.rerank_scores('a', ['b'])"
# Hugging Face Spaces runs containers as a non-root user: make our data folder writable.
RUN chmod -R 777 /app/data
EXPOSE 7860
CMD ["python", "scripts/run_all.py"]
