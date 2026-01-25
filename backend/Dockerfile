FROM python:3.9-slim

WORKDIR /app

COPY backend.py config.json index.html .

RUN mkdir uploads

EXPOSE 54000

CMD ["python3", "backend.py"]
