FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Default database path — overridden to /data/taskbot.db by fly.toml on Fly.io
# so that the database lives on the persistent volume and survives redeployments.
ENV DATABASE_PATH=/data/taskbot.db

# Ensure the data directory exists for local Docker runs
RUN mkdir -p /data

CMD ["python", "bot.py"]
