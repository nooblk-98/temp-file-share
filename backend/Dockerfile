FROM python:3.9-slim

WORKDIR /app

COPY backend.py app.py config.json .
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

RUN mkdir uploads

EXPOSE 54000

CMD ["python3", "backend.py"]
