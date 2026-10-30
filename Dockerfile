FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Logların tamponlanmadan terminale akmasını sağlar
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
