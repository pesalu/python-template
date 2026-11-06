FROM python:3.12-slim

WORKDIR /app
# README.md is needed because pyproject.toml declares it as the package readme.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Mount a host folder here to keep the results.
WORKDIR /data
ENV PYTHONUNBUFFERED=1

CMD ["web-scraper", "--help"]
