FROM python:3.13-slim

WORKDIR /app

# MySQL client only (mysqldump/mysql for backup/restore). No compiler needed:
# pymysql is pure Python, gevent and cryptography ship prebuilt wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
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
