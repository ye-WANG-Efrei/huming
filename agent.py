import asyncio
import subprocess
import json
import hmac
import hashlib
import base64
import time
import opuslib
import websockets
from music import lookup
import os

DEVICE_ID = "DF:3F:F1:7A:6A:10"   # 目标设备（小智）
BRIDGE_DEVICE_ID = "bridge_client_01"  # bridge 自己的 ID
CLIENT_ID = "web_test_client"
AUTH_KEY = "e334d263-2272-418d-b8eb-ed9bedc5e49f"
WS_URL = "ws://8.138.203.141:8000/xiaozhi/v1/"
CACHE_DIR = "opus_cache"

# AUTH_KEY = "38077437-ebe1-4cb0-b2cd-c422935031f0"  # 本地测试的 key
# WS_URL = "ws://10.221.140.162:8000/xiaozhi/v1/"     # 本地 IP

os.makedirs(CACHE_DIR, exist_ok=True)

def generate_token(client_id, device_id, secret_key):
    ts = int(time.time())
    content = f"{client_id}|{device_id}|{ts}"
    sig = hmac.new(secret_key.encode(), content.encode(), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{signature}.{ts}"

async def connect():
    token = generate_token(CLIENT_ID, BRIDGE_DEVICE_ID, AUTH_KEY)
    url = f"{WS_URL}?device-id={BRIDGE_DEVICE_ID}&client-id={CLIENT_ID}&authorization=Bearer+{token}&bridge=true"

    ws = await websockets.connect(url)

    await ws.send(json.dumps({
        "type": "hello",
        "version": 1,
        "transport": "websocket",
        "bridge": True,
        "target_device": DEVICE_ID,
        "audio_params": {
            "format": "opus",
            "sample_rate": 16000,
            "channels": 1,
            "frame_duration": 60
        }
    }))

    msg = await ws.recv()
    data = json.loads(msg)
    assert data["type"] == "hello", f"握手失败: {data}"
    print("握手OK, session_id =", data["session_id"])
    return ws

async def stream_music(ws, song_keyword, start_seconds, end_seconds):
    cache_file = os.path.join(CACHE_DIR, f"{song_keyword}_{int(start_seconds)}.opus")

    if os.path.exists(cache_file):
        print(f"命中缓存: {cache_file}")
        with open(cache_file, 'rb') as f:
            while True:
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    break
                length = int.from_bytes(length_bytes, 'big')
                opus_data = f.read(length)
                await ws.send(opus_data)
        print("推流完成（缓存）")
        return

    print("无缓存，开始下载...")
    duration = end_seconds - start_seconds

    proc = subprocess.Popen(
        ['yt-dlp', '-o', '-', '--quiet', '-f', 'bestaudio', f'scsearch1:{song_keyword}'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    ffmpeg = subprocess.Popen(
        ['ffmpeg', '-i', 'pipe:0',
        '-ss', str(int(start_seconds)),
        '-t', str(duration),
        '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1'],
        stdin=proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )

    enc = opuslib.Encoder(16000, 1, opuslib.APPLICATION_AUDIO)
    frame_count = 0

    with open(cache_file, 'wb') as cache:
        while True:
            pcm = ffmpeg.stdout.read(1920)
            if len(pcm) < 1920:
                break
            opus_data = enc.encode(pcm, 960)
            cache.write(len(opus_data).to_bytes(2, 'big') + opus_data)
            await ws.send(opus_data)
            frame_count += 1
            if frame_count % 50 == 0:
                print(f"已推 {frame_count} 帧")

    print(f"推流完成，共 {frame_count} 帧")

async def main():
    print("开始查歌...")
    result = await lookup("七溜八溜", "waiya")
    print(f"找到: {result['song_name']} @ {result['seconds']}s ~ {result['end_seconds']}s")

    print("连接WebSocket...")
    ws = await connect()
    print("开始推流...")
    await stream_music(ws, "waiya", result["seconds"], result["end_seconds"])
    await ws.close()
    print("推流完成")

    
if __name__ == "__main__":
    asyncio.run(main())