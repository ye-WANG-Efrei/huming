"""
给 lyric_index 添加别名，让某个词直接命中已有歌词条目。
用法：python add_alias.py <别名> <已有歌词原文>

例：python add_alias.py "7687" "七溜八溜"
"""
import sys
import json
import os
from filelock import FileLock

CACHE_FILE = "music_cache.json"
_CACHE_LOCK = FileLock(CACHE_FILE + ".lock")


def add_alias(alias: str, target_lyric: str):
    try:
        with _CACHE_LOCK:
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)

            index = cache.get("lyric_index", {})

            if target_lyric not in index:
                candidates = [k for k in index if target_lyric in k or k in target_lyric]
                if candidates:
                    print(f"未找到精确匹配 '{target_lyric}'，候选：")
                    for c in candidates[:10]:
                        print(f"  {c!r} → {index[c]['song_name']}")
                else:
                    print(f"未找到 '{target_lyric}'，lyric_index 里没有这条歌词。")
                return

            if alias in index and alias != target_lyric:
                print(f"警告：'{alias}' 已存在（→ {index[alias]['song_name']}），将被覆盖。")

            entry = index[target_lyric]
            index[alias] = entry

            tmp = CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            os.replace(tmp, CACHE_FILE)

    except FileNotFoundError:
        print(f"错误：找不到 {CACHE_FILE}，请确认在正确目录下运行。")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：{CACHE_FILE} 格式损坏（{e}），请检查文件内容。")
        sys.exit(1)

    print(f"已添加别名: {alias!r} → {entry['song_name']} @ {entry['seconds']}s")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python add_alias.py <别名> <已有歌词原文>")
        print('例:   python add_alias.py "7687" "七溜八溜"')
        sys.exit(1)
    add_alias(sys.argv[1], sys.argv[2])
