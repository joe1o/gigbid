# Dockerfile - one image for the hosted deployment (Render free web service, 512 MB RAM).
# Stage 1 builds the React app; stage 2 is the Python app that serves it.
#
# On the free host everything runs in ONE process to fit in memory: GigSim and the three MCP
# servers run in-process (GIGBID_INPROCESS=1), with one model thread, small batches and one
# graph run at a time (measured peak ~440 MB). Locally, scripts/run_all.py runs every server as
# its own process instead (needed for the "kill the marketplace server" demo).

# ---- stage 1: web app ----
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npx vite build

# ---- stage 2: Python app ----
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PORT=10000 \
    GIGBID_INPROCESS=1 \
    GIGBID_RUN_SLOTS=1 \
    GIGBID_MODEL_THREADS=1 \
    GIGBID_MODEL_BATCH=8 \
    OMP_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1
COPY . .
COPY --from=web /web/dist apps/web/dist
RUN pip install --no-cache-dir -e .
# Download the two open models into the image now, so the first request is not slow.
RUN python -c "from rag import models; models.embed_query('warm up'); models.rerank_scores('a', ['b'])"
RUN chmod -R 777 /app/data
EXPOSE 10000
CMD ["python", "scripts/serve_api.py"]
