FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Database lives on the persistent volume mounted at /data
ENV DATABASE_PATH=/data/taskbot.db

# Ensure the data directory exists
RUN mkdir -p /data

CMD ["python", "src/bot.py"]
