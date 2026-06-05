"""
测试 LLM 歌词识别 prompt 的脚本。
不需要设备在线，直接调 GLM API，看不同输入下 LLM 输出什么。

用法：
    python test_llm.py

在 CASES 里加测试用例，期望输出填 "JSON"（触发播放）或 "EMPTY"（静默）或 "MCP"（调工具）。
"""

import os
import re
from openai import OpenAI

# 从环境变量读，也可以直接写死
GLM_API_KEY = os.environ.get("GLM_API_KEY", "替换成你的GLM API Key")
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
MODEL = "glm-4-flash"

# 和管理后台一致的 prompt（粘贴你的完整 prompt）
SYSTEM_PROMPT = """
[角色设定]
你是一个嵌入对话中的"接歌"助手，懂华语流行歌、网络热歌和经典老歌。
核心能力：用户随口说话时，自动识别并接入对应歌曲片段。

[三种情况，三种处理]

情况一：用户明确要求播放某首歌
例：「来一首稻香」「放周杰伦的歌」「播放爱如火」「我想听XXX」
→ 调用 self.online_music.play_music 工具播放，不输出 JSON

情况二：用户说话中自然出现歌词片段或可识别的歌名（接梗场景）
→ 先输出"嗯。"，紧接着输出 JSON（不换行不加空格）：
嗯。{"action":"play","lyric":"<识别到的关键歌词或歌名>"}

情况三：纯情绪/日常表达，没有具体歌名或可识别歌词
→ 什么都不输出，保持沉默

[判断标准]
- 含有具体歌名 → 情况一（主动请求）或情况二（随口提及）
- 含有可识别歌词片段 → 情况二
- 只有情绪词、形容词，没有具体歌名歌词 → 情况三

[播放指令格式]
情况二固定格式：嗯。{"action":"play","lyric":"<歌词或歌名>"}
""".strip()

# 测试用例：(输入, 期望类型)
# 期望类型: "JSON"=触发我们的bridge  "EMPTY"=静默  "MCP"=调工具播放
CASES = [
    ("他真的爱如火啊",       "JSON"),
    ("故事的小黄花",         "JSON"),
    ("北京欢迎你",           "JSON"),
    ("APT APT",             "JSON"),
    ("科目三",               "JSON"),
    ("我今天很emo",          "EMPTY"),
    ("好累啊今天",           "EMPTY"),
    ("你好",                 "EMPTY"),
    ("来一首稻香",           "MCP"),
    ("放周杰伦的歌",         "MCP"),
    ("播放爱如火",           "MCP"),
    ("确认过眼神我遇见对的人", "JSON"),
    ("就算在小小的天空",      "JSON"),
    ("今天超燃",             "EMPTY"),
]

PLAY_JSON_RE = re.compile(r'嗯。\s*\{"action"\s*:\s*"play"')


def classify(output: str) -> str:
    """判断实际输出属于哪种类型"""
    stripped = output.strip()
    if not stripped:
        return "EMPTY"
    if PLAY_JSON_RE.search(stripped):
        return "JSON"
    # 有文字输出但不是 JSON → 可能是 MCP 工具调用的描述或其他
    return "MCP/OTHER"


def run_tests():
    client = OpenAI(api_key=GLM_API_KEY, base_url=GLM_BASE_URL)

    passed = 0
    failed = 0

    print(f"{'输入':<25} {'期望':<8} {'实际':<12} {'输出预览'}")
    print("-" * 80)

    for user_input, expected in CASES:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_input},
            ],
            temperature=0,
            max_tokens=100,
        )
        output = resp.choices[0].message.content or ""
        actual = classify(output)

        ok = (actual == expected) or (expected == "MCP" and actual in ("MCP/OTHER", "MCP"))
        status = "✓" if ok else "✗"
        if ok:
            passed += 1
        else:
            failed += 1

        preview = output.replace("\n", "\\n")[:40]
        print(f"{status} {user_input:<23} {expected:<8} {actual:<12} {preview}")

    print("-" * 80)
    print(f"通过 {passed}/{passed+failed}，失败 {failed}/{passed+failed}")


if __name__ == "__main__":
    run_tests()
