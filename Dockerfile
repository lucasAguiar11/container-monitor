FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN apk add --no-cache gcc python3-dev musl-dev linux-headers \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del gcc python3-dev musl-dev linux-headers
COPY monitor.py .
CMD ["python", "monitor.py"]
