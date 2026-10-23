FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken \
    NLTK_DATA=/app/nltk_data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"
RUN python -m spacy download en_core_web_sm
RUN python -m nltk.downloader -d /app/nltk_data cmudict

COPY agents/ agents/
COPY config/ config/
COPY backend/ backend/

WORKDIR /app/backend
ENV PYTHONPATH=/app
EXPOSE 8000

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]