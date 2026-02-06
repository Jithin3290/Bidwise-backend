# Base stage
FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files for development
FROM base AS development
COPY . .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
