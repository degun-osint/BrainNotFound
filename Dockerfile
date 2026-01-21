FROM python:3.13-slim

WORKDIR /app

# Install system dependencies (including MySQL client for backup/restore)
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    default-mysql-client \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory for quiz files
RUN mkdir -p uploads

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]
