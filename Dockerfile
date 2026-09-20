FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_PATH=/app/data/workspace.db PORT=8080
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY --chown=app:app server ./server
COPY --chown=app:app src ./src
COPY --chown=app:app designs ./designs
COPY --chown=app:app index.html login.html design-preview.html screens.json ./
RUN mkdir -p /app/data && chown app:app /app/data
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3)"
CMD ["python", "-m", "server.production"]
