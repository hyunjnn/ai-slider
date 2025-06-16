FROM python:3.12-slim-bookworm

WORKDIR /app
COPY . /app

ENV PYTHONPATH=/app

RUN pip install --upgrade pip && pip install -r requirements.txt

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]