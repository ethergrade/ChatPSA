FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup --system chatpsa && adduser --system --ingroup chatpsa chatpsa
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY knowledge/guides ./knowledge/guides
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data /app/knowledge/tenant && chown -R chatpsa:chatpsa /app

USER chatpsa
EXPOSE 8765
CMD ["chatpsa-web"]
