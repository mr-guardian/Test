FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Eksik olan Chromium ikililerini ve sistem bağımlılıklarını kur
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
