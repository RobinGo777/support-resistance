FROM python:3.11.9-slim

# Встановлення системних залежностей для matplotlib
RUN apt-get update && apt-get install -y \
    libfreetype6-dev \
    libpng-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Matplotlib без GUI
ENV MPLBACKEND=Agg

CMD ["python", "bot.py"]
