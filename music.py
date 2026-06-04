import subprocess
import json
import os
import asyncio
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer

CACHE_FILE = "music_cache.json"
EMBED_CACHE_FILE = "lyric_embeddings.pkl"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBED_THRESHOLD = 0.88

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"加载 embedding 模型: {EMBED_MODEL} ...")
        _model = SentenceTransformer(EMBED_MODEL)
        print("模型加载完成")
    return _model


def _load_embed_cache() -> dict:
    """返回 {lyric_text: np.ndarray}"""
    if os.path.exists(EMBED_CACHE_FILE):
        with open(EMBED_CACHE_FILE, "rb") as f:
            return pickle.load(f)
    return {}


def _save_embed_cache(cache: dict):
    with open(EMBED_CACHE_FILE, "wb") as f:
        pickle.dump(cache, f)


def _embed_search(query: str, lyric_index: dict) -> dict | None:
    """在 lyric_index 里用 cosine similarity 找最相似的歌词行，返回对应结果或 None。"""
    if not lyric_index:
        return None

    model = _get_model()
    embed_cache = _load_embed_cache()

    # 找出还没有 embedding 的歌词行
    missing = [t for t in lyric_index if t not in embed_cache]
    if missing:
        print(f"计算 {len(missing)} 条新歌词的 embedding ...")
        vecs = model.encode(missing, normalize_embeddings=True, show_progress_bar=False)
        for text, vec in zip(missing, vecs):
            embed_cache[text] = vec
        _save_embed_cache(embed_cache)

    # 编码 query
    query_vec = model.encode([query], normalize_embeddings=True)[0]

    # 计算与所有已知歌词的相似度
    texts = list(lyric_index.keys())
    matrix = np.stack([embed_cache[t] for t in texts])  # (N, D)
    sims = matrix @ query_vec  # cosine sim，因为已 normalize

    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])
    best_text = texts[best_idx]

    print(f"embedding 最佳匹配: {best_text!r}  相似度={best_sim:.3f}")

    if best_sim >= EMBED_THRESHOLD:
        return lyric_index[best_text]
    return None


async def lookup(lyric_text: str, song_keyword: str = None) -> dict:
    if song_keyword is None:
        song_keyword = lyric_text
    cache = _load_cache()

    # 1. 精确命中
    if lyric_text in cache["lyric_index"]:
        return cache["lyric_index"][lyric_text]

    # 2. embedding 搜索已有歌词库
    embed_result = _embed_search(lyric_text, cache["lyric_index"])
    if embed_result is not None:
        return embed_result

    # 3. 走 ncm-cli 搜索 + 歌词匹配
    song = search_song(song_keyword)
    lines = get_lyric(song["encrypted_id"], song["name"])

    result = None
    for i, line in enumerate(lines):
        if lyric_text in line["text"]:
            end_index = min(i + 6, len(lines) - 1)
            result = {
                "song_name": song["name"],
                "artist": song["artist"],
                "original_id": song["original_id"],
                "encrypted_id": song["encrypted_id"],
                "seconds": line["time"],
                "end_seconds": lines[end_index]["time"],
            }
            break

    # 没找到完整匹配，用滑动窗口子串（最少4字）模糊搜索
    if result is None:
        min_len = 4
        for window in range(len(lyric_text), min_len - 1, -1):
            for start in range(len(lyric_text) - window + 1):
                substring = lyric_text[start:start + window]
                for i, line in enumerate(lines):
                    if substring in line["text"]:
                        end_index = min(i + 6, len(lines) - 1)
                        result = {
                            "song_name": song["name"],
                            "artist": song["artist"],
                            "original_id": song["original_id"],
                            "encrypted_id": song["encrypted_id"],
                            "seconds": line["time"],
                            "end_seconds": lines[end_index]["time"],
                        }
                        break
                if result:
                    break
            if result:
                break

    # 还是没找到，从歌曲开头播
    if result is None and lines:
        end_index = min(6, len(lines) - 1)
        result = {
            "song_name": song["name"],
            "artist": song["artist"],
            "original_id": song["original_id"],
            "encrypted_id": song["encrypted_id"],
            "seconds": lines[0]["time"],
            "end_seconds": lines[end_index]["time"],
        }

    asyncio.create_task(_save_lyric_index(lines, song))
    return result


async def _save_lyric_index(lines: list, song: dict):
    cache = _load_cache()
    for i, line in enumerate(lines):
        if line["text"] in cache["lyric_index"]:  # 只保留第一次出现
            continue
        end_index = min(i + 6, len(lines) - 1)
        cache["lyric_index"][line["text"]] = {
            "song_name": song["name"],
            "artist": song["artist"],
            "original_id": song["original_id"],
            "encrypted_id": song["encrypted_id"],
            "seconds": line["time"],
            "end_seconds": lines[end_index]["time"],
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


def _ensure_ncm_login():
    check = subprocess.run(
        ["ncm-cli", "login", "--check", "--output", "json"],
        capture_output=True, text=True
    )
    if '"success": true' not in check.stdout:
        raise RuntimeError("ncm-cli 未登录，请先运行: ncm-cli login")


def search_song(keyword: str) -> dict:
    cache = _load_cache()
    if keyword in cache["search"]:
        return cache["search"][keyword]

    _ensure_ncm_login()
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

    if not lyric_text:
        print(f"歌曲 {song_name} 没有歌词数据")
        return []

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
