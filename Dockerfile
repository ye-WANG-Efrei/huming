FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libopus-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# install yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod +x /usr/local/bin/yt-dlp

# install ncm-cli
RUN pip install ncm-cli

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py music.py ./

ENV DEVICE_ID=DF:3F:F1:7A:6A:10
ENV BRIDGE_DEVICE_ID=bridge_client_01
ENV CLIENT_ID=web_test_client
ENV AUTH_KEY=e334d263-2272-418d-b8eb-ed9bedc5e49f
ENV WS_URL=ws://8.138.203.141:8000/xiaozhi/v1/
ENV CACHE_DIR=opus_cache

EXPOSE 8888

CMD ["python", "agent.py"]
