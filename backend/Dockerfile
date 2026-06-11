FROM python:3.12-alpine

RUN apk add --no-cache \
    font-noto-cjk \
    freetype-dev \
    libpng-dev \
    gcc \
    musl-dev \
    python3-dev

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python3 -c "import matplotlib, os, shutil; shutil.rmtree(os.path.expanduser('~/.cache/matplotlib'), ignore_errors=True)"
COPY . .

VOLUME /app/data

ENV ROOT_DIR=/app/data/

EXPOSE 8000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "300", "app:app"]
