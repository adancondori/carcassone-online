FROM python:3.12-slim

WORKDIR /code

# Install dependencies first for better layer caching
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application code
COPY . .

# Ensure data directory exists
RUN mkdir -p /code/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
