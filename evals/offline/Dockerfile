FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e .
CMD ["python", "-m", "evaluator.cli", "run-agents", "--source", "langfuse"]
