# Playwright runtime with browsers preinstalled (Chromium/WebKit/Firefox)
FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY grabagun_giveaway_once.py .

CMD ["python", "/app/grabagun_giveaway_once.py"]
