FROM python:3.13-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN pip install --no-cache-dir .

EXPOSE 8002

CMD ["uvicorn", "ingen_prompt_tuner.main:app", "--host", "0.0.0.0", "--port", "8002"]
