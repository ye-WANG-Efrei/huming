import asyncio
import subprocess
import json
import hmac
import hashlib
import base64
import time
import opuslib
import websockets
from aiohttp import web
from music import lookup, _load_cache, _embed_search
import os

DEVICE_ID = os.environ.get("DEVICE_ID", "DF:3F:F1:7A:6A:10")
BRIDGE_DEVICE_ID = os.environ.get("BRIDGE_DEVICE_ID", "bridge_client_01")
CLIENT_ID = os.environ.get("CLIENT_ID", "web_test_client")
AUTH_KEY = os.environ.get("AUTH_KEY", "e334d263-2272-418d-b8eb-ed9bedc5e49f")
WS_URL = os.environ.get("WS_URL", "ws://8.138.203.141:8000/xiaozhi/v1/")
CACHE_DIR = os.environ.get("CACHE_DIR", "opus_cache")

os.makedirs(CACHE_DIR, exist_ok=True)


def generate_token(client_id, device_id, secret_key):
    ts = int(time.time())
    content = f"{client_id}|{device_id}|{ts}"
    sig = hmac.new(secret_key.encode(), content.encode(), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{signature}.{ts}"


async def connect(target_device=None):
    token = generate_token(CLIENT_ID, BRIDGE_DEVICE_ID, AUTH_KEY)
    url = f"{WS_URL}?device-id={BRIDGE_DEVICE_ID}&client-id={CLIENT_ID}&authorization=Bearer+{token}&bridge=true"

    ws = await websockets.connect(url)

    await ws.send(json.dumps({
        "type": "hello",
        "version": 1,
        "transport": "websocket",
        "bridge": True,
        "target_device": target_device or DEVICE_ID,
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


async def stream_music(ws, song_keyword, start_seconds, end_seconds, artist=None, original_id=None):
    cache_name = f"{original_id}_{int(start_seconds)}" if original_id else f"{song_keyword}_{int(start_seconds)}"
    cache_file = os.path.join(CACHE_DIR, f"{cache_name}.opus")

    if os.path.exists(cache_file):
        print(f"命中缓存: {cache_file}")
        await ws.send(json.dumps({"type": "tts_bridge", "state": "start", "text": "♪"}))
        with open(cache_file, 'rb') as f:
            while True:
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    break
                length = int.from_bytes(length_bytes, 'big')
                opus_data = f.read(length)
                await ws.send(opus_data)
        await ws.send(json.dumps({"type": "tts_bridge", "state": "stop"}))
        print("推流完成（缓存）")
        return

    print("无缓存，开始下载...")
    duration = end_seconds - start_seconds

    ncm_url = f'https://music.163.com/song?id={original_id}' if original_id else f'scsearch1:{song_keyword} {artist}'

    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp_template = cache_file + ".tmp.%(ext)s"
    yt_result = subprocess.run(
        ['yt-dlp', '-o', tmp_template, '--quiet', '-f', 'bestaudio', ncm_url],
        stderr=subprocess.PIPE
    )
    yt_err = yt_result.stderr.decode(errors="ignore").strip()
    if yt_err:
        print(f"[yt-dlp stderr] {yt_err}")
    if yt_result.returncode != 0:
        print(f"yt-dlp 下载失败，returncode={yt_result.returncode}")
        return

    # 找到 yt-dlp 实际存的文件（扩展名不确定）
    import glob
    tmp_files = glob.glob(cache_file + ".tmp.*")
    if not tmp_files:
        print("yt-dlp 下载失败，找不到临时文件")
        return
    tmp_file = tmp_files[0]
    print(f"下载完成: {tmp_file}")

    # 检查文件实际时长，防止 start_seconds 超出
    probe = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', tmp_file],
        capture_output=True, text=True
    )
    probe_data = json.loads(probe.stdout)
    file_duration = float(probe_data["format"]["duration"])
    print(f"文件时长: {file_duration:.1f}s，请求起点: {start_seconds:.1f}s")
    if start_seconds >= file_duration:
        print(f"起点超出文件时长，从头播放")
        start_seconds = 0

    ffmpeg = subprocess.Popen(
        ['ffmpeg', '-ss', str(int(start_seconds)),
        '-i', tmp_file,
        '-t', str(duration),
        '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    enc = opuslib.Encoder(16000, 1, opuslib.APPLICATION_AUDIO)
    frame_count = 0

    await ws.send(json.dumps({"type": "tts_bridge", "state": "start", "text": "♪"}))
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
    await ws.send(json.dumps({"type": "tts_bridge", "state": "stop"}))

    ffmpeg_err = ffmpeg.stderr.read().decode(errors="ignore").strip()
    if ffmpeg_err:
        print(f"[ffmpeg stderr] {ffmpeg_err[-500:]}")
    print(f"推流完成，共 {frame_count} 帧")
    if os.path.exists(tmp_file):
        os.remove(tmp_file)


async def play(lyric_text: str, device_id: str = None):
    print(f"收到播放请求: {lyric_text} → 设备: {device_id or DEVICE_ID}")
    result = await lookup(lyric_text)
    print(f"找到: {result['song_name']} @ {result['seconds']}s ~ {result['end_seconds']}s")
    ws = await connect(target_device=device_id)
    await stream_music(ws, result["song_name"], result["seconds"], result["end_seconds"],
                       artist=result.get("artist"), original_id=result.get("original_id"))
    await ws.close()
    print("推流完成")


async def handle_play(request):
    data = await request.json()
    lyric_text = data.get("lyric")
    if not lyric_text:
        return web.json_response({"error": "missing lyric"}, status=400)
    device_id = data.get("device_id", DEVICE_ID)
    asyncio.create_task(play(lyric_text, device_id))
    return web.json_response({"status": "ok"})


async def handle_check_play(request):
    """只查本地缓存（不走 ncm-cli），命中则触发播放。"""
    data = await request.json()
    lyric_text = data.get("lyric")
    if not lyric_text:
        return web.json_response({"status": "not_found"})
    device_id = data.get("device_id", DEVICE_ID)

    cache = _load_cache()
    result = cache["lyric_index"].get(lyric_text)
    if result is None:
        result = _embed_search(lyric_text, cache["lyric_index"])
    if result is None:
        return web.json_response({"status": "not_found"})

    print(f"缓存命中: {lyric_text} → {result['song_name']} @ {result['seconds']}s")
    asyncio.create_task(play(lyric_text, device_id))
    return web.json_response({"status": "playing"})


HOST = "0.0.0.0"
PORT = 8888

if __name__ == "__main__":
    app = web.Application()
    app.router.add_post("/play", handle_play)
    app.router.add_post("/check_play", handle_check_play)
    print(f"Bridge server 启动，监听 http://{HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
