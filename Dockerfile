FROM python:3.12-slim

WORKDIR /app
# README.md is needed because pyproject.toml declares it as the package readme.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Mount a volume here to keep the results.
WORKDIR /data
ENV PYTHONUNBUFFERED=1

# Default job: needs SCRAPER_URL (and optionally SCRAPER_STATE_PATH). Override the command to run
# any single tool, e.g. `web-scraper-fetch --help`.
CMD ["web-scraper-run"]
