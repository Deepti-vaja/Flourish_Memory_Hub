FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files to disk and ensure logging goes straight to stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies needed for psycopg and pgvector if necessary
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
# First copy pyproject.toml to leverage Docker cache
COPY pyproject.toml /app/

# Install the dependencies from pyproject.toml
RUN pip install --no-cache-dir .

# Copy the rest of the application
COPY . /app/

# Expose port
EXPOSE 8000

# The startup command runs alembic migrations then starts the uvicorn server
# This guarantees 0-manual-step launch and is fully idempotent.
CMD ["sh", "-c", "alembic -c app/database/migrations/alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
