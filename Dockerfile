FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    gcc \
    libffi-dev \
    libssl-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY . .

RUN mkdir -p bot

CMD ["python3", "run.py"]
