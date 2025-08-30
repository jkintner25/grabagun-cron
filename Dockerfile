FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app
RUN pip install --no-cache-dir playwright==1.55.0

COPY grabagun_giveaway_once.py .

CMD ["python", "/app/grabagun_giveaway_once.py"]
