FROM python:3.12-slim
WORKDIR /app
COPY agent_framework /agent_framework
COPY agent_template_backend /app
RUN pip install --no-cache-dir -e /agent_framework -r requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
