# Playwright runtime with browsers preinstalled (Chromium/WebKit/Firefox)
FROM mcr.microsoft.com/playwright/python:v1.47.2-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the single-shot script
COPY grabagun_giveaway_once.py .

# Default command (Render can override with the "Command" field)
CMD ["python", "/app/grabagun_giveaway_once.py"]
