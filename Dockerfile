# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories with correct permissions
RUN mkdir -p logs data backups \
    && chown -R 1000:1000 /app \
    && chmod -R 755 /app

# Copy project files
COPY . .

# Set correct permissions for copied files
RUN chown -R 1000:1000 /app \
    && chmod -R 755 /app \
    && chmod -R 777 /app/logs

# Create non-root user
RUN useradd -u 1000 -m botuser
USER botuser

# Command to run the application
CMD ["python", "-m", "src.bot.main"] 