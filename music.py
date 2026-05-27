import subprocess
import json
import os
import asyncio

CACHE_FILE = "music_cache.json"


async def lookup(lyric_text: str, song_keyword: str) -> dict:
    cache = _load_cache()

    # 1. 命中缓存直接返回
    if lyric_text in cache["lyric_index"]:
        return cache["lyric_index"][lyric_text]

    # 2. 没有缓存，搜歌 + 取歌词
    song = search_song(song_keyword)
    lines = get_lyric(song["encrypted_id"], song["name"])

    # 3. 找到对应歌词的秒数
    result = None
    for line in lines:
        if lyric_text in line["text"]:
            result = {
                "song_name": song["name"],
                "encrypted_id": song["encrypted_id"],
                "seconds": line["time"],
            }
            break

    # 4. 先返回结果，异步存缓存
    asyncio.create_task(_save_lyric_index(lines, song))
    return result



async def _save_lyric_index(lines: list, song: dict):
    cache = _load_cache()
    for line in lines:
        cache["lyric_index"][line["text"]] = {
            "song_name": song["name"],
            "encrypted_id": song["encrypted_id"],
            "seconds": line["time"],
        }
    _save_cache(cache)

    
def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {"search": {}, "lyric": {}, "lyric_index": {}}

def _save_cache(cache: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False)


# 用关键词搜索歌曲
def search_song(keyword: str) -> dict:
    cache = _load_cache()
    if keyword in cache["search"]:
        return cache["search"][keyword]

    result = subprocess.run(
        ["ncm-cli", "search", "song", "--keyword", keyword, "--limit", "1", "--output", "json"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    song = data["data"]["records"][0]
    song_data = {
        "name": song["name"],
        "artist": song["artists"][0]["name"],
        "original_id": song["originalId"],
        "encrypted_id": song["id"],
        "duration": song["duration"] // 1000,
    }
    cache["search"][keyword] = song_data
    _save_cache(cache)
    return song_data
# 用歌曲ID获取歌词timestamp和歌词文本

def get_lyric(encrypted_id: str, song_name: str) -> list:
    cache = _load_cache()
    if encrypted_id in cache["lyric"]:
        return cache["lyric"][encrypted_id]

    result = subprocess.run(
        ["ncm-cli", "song", "lyric", "--songId", encrypted_id, "--output", "json"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    lyric_text = data["data"]["lyric"]

    lines = []
    for line in lyric_text.strip().split("\n"):
        if line.startswith("[") and "]" in line:
            time_str = line[1:line.index("]")]
            text = line[line.index("]") + 1:].strip()
            if not text:
                continue
            try:
                parts = time_str.split(":")
                seconds = int(parts[0]) * 60 + float(parts[1])
                lines.append({"time": seconds, "text": text})
                cache["lyric_index"][text] = {
                    "song_name": song_name,
                    "encrypted_id": encrypted_id,
                    "seconds": seconds,
                }
            except:
                continue

    cache["lyric"][encrypted_id] = lines
    _save_cache(cache)
    return lines


if __name__ == "__main__":
    result = search_song("waiya")
    print(result)
    lyrics = get_lyric(result["encrypted_id"], result["name"])
    for line in lyrics[:5]:
        print(line)