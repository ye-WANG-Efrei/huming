"""
给 lyric_index 添加别名，让某个词直接命中已有歌词条目。
用法：python add_alias.py <别名> <已有歌词原文>

例：python add_alias.py "7687" "七溜八溜"
"""
import sys
import json

CACHE_FILE = "music_cache.json"

def add_alias(alias: str, target_lyric: str):
    with open(CACHE_FILE, encoding="utf-8") as f:
        cache = json.load(f)

    index = cache.get("lyric_index", {})

    if target_lyric not in index:
        # 模糊查找：显示包含关键词的候选
        candidates = [k for k in index if target_lyric in k or k in target_lyric]
        if candidates:
            print(f"未找到精确匹配 '{target_lyric}'，候选：")
            for c in candidates[:10]:
                print(f"  {c!r} → {index[c]['song_name']}")
        else:
            print(f"未找到 '{target_lyric}'，lyric_index 里没有这条歌词。")
        return

    entry = index[target_lyric]
    index[alias] = entry
    cache["lyric_index"] = index

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

    print(f"已添加别名: {alias!r} → {entry['song_name']} @ {entry['seconds']}s")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python add_alias.py <别名> <已有歌词原文>")
        print('例:   python add_alias.py "7687" "七溜八溜"')
        sys.exit(1)
    add_alias(sys.argv[1], sys.argv[2])
