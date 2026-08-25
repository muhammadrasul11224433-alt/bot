FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py config.py i18n.py media.py ./

RUN mkdir -p /app/downloads

ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "bot.py"]
