# Dockerfile for the Portfolio MCP server on its own (stdio transport, for Claude Desktop and other hosts).
# Build from the repo root:  docker build -t gigbid-portfolio-mcp -f mcp_servers/portfolio/Dockerfile .
# Run:                       docker run -i --rm -v /path/to/my_portfolio.json:/data/portfolio.json gigbid-portfolio-mcp
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HUB_DISABLE_SYMLINKS_WARNING=1 LANGSMITH_TRACING=false \
    PORTFOLIO_PATH=/data/portfolio.json
COPY . .
RUN pip install --no-cache-dir -e .
# Download the two small CPU models now, so the first search is fast.
RUN python -c "from rag import models; models.embed_query('warm up'); models.rerank_scores('a', ['b'])"
# Default portfolio: the sample web developer. Mount your own file over it with -v.
RUN mkdir -p /data && cp data/personas/web_developer/portfolio.json /data/portfolio.json && chmod -R 777 /app/data
ENTRYPOINT ["python", "-m", "mcp_servers.portfolio.server", "--stdio"]
