# xiaozhi-bridge

将歌词关键词转化为音频推流，通过 bridge WebSocket 连接直接向小智设备播放对应歌曲片段。

## 工作流程

```
用户说话 → ASR → LLM识别歌词关键词 → POST /play → 查歌定位时间戳 → yt-dlp下载 → Opus编码 → bridge推流 → 设备播放
```

## 本地开发

```bash
python -m venv huming-venv
source huming-venv/bin/activate  # Windows: huming-venv\Scripts\activate
pip install -r requirements.txt
python agent.py
```

测试：
```bash
curl -X POST http://localhost:8888/play \
  -H "Content-Type: application/json" \
  -d '{"lyric":"WAIYA"}'
```

## 本地开发 + 内网穿透（调试用）

在本地跑通流程，通过内网穿透让 ECS 上的 xiaozhi-server 能调到本地的 agent.py。

### 方式1：SSH 远程转发（推荐，无需额外工具）

```bash
# 启动 agent.py
python agent.py

# 另一个终端，建立 SSH 隧道
# ECS 的 localhost:8888 → 本地 localhost:8888
ssh -R 8888:localhost:8888 xiaozhi-ecs
```

隧道建立后，ECS 上的 xiaozhi-server 调 `localhost:8888` 就能打到你本地的 agent.py。
隧道只监听 ECS 本机，不对外暴露，无需开放安全组端口。

### 方式2：ngrok

```bash
# 安装 ngrok：https://ngrok.com/download
ngrok http 8888
```

ngrok 会输出一个公网地址，把 xiaozhi-server 里调用的 `localhost:8888` 替换成该地址。

---

## Docker 部署到新服务器

### 1. 构建镜像

```bash
docker build -t wangyeee/xiaozhi-bridge .
docker push wangyeee/xiaozhi-bridge
```

### 2. 在新服务器上运行

```bash
docker run -d \
  --name xiaozhi-bridge \
  --restart always \
  -p 8888:8888 \
  -e DEVICE_ID=DF:3F:F1:7A:6A:10 \
  -e AUTH_KEY=e334d263-2272-418d-b8eb-ed9bedc5e49f \
  -e WS_URL=ws://8.138.203.141:8000/xiaozhi/v1/ \
  -v /data/xiaozhi-bridge/opus_cache:/app/opus_cache \
  -v /data/xiaozhi-bridge/music_cache.json:/app/music_cache.json \
  wangyeee/xiaozhi-bridge
```

默认值已内置，不传环境变量也能跑。只在需要修改时传对应的 `-e` 参数。

### 3. 登录 ncm-cli（首次部署必须）

```bash
docker exec -it xiaozhi-bridge ncm-cli login
```

### 4. 验证服务

```bash
curl -X POST http://<服务器IP>:8888/play \
  -H "Content-Type: application/json" \
  -d '{"lyric":"WAIYA"}'
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEVICE_ID` | `DF:3F:F1:7A:6A:10` | 目标小智设备 MAC |
| `AUTH_KEY` | 见代码 | xiaozhi-server 鉴权 key |
| `WS_URL` | `ws://8.138.203.141:8000/xiaozhi/v1/` | xiaozhi-server 地址 |
| `BRIDGE_DEVICE_ID` | `bridge_client_01` | bridge 客户端标识 |
| `CACHE_DIR` | `opus_cache` | Opus 缓存目录 |

## 独立服务器部署注意事项

agent.py 部署在独立服务器（非 ECS 本机）时：
1. 独立服务器安全组放行 8888 端口
2. xiaozhi-server 里的调用地址从 `localhost:8888` 改为 `<独立服务器IP>:8888`

## xiaozhi-server 改动

见 `xiaozhi-server-patch/` 目录，需将其中文件覆盖到 xiaozhi-esp32-server 对应路径并重启服务。

---

## 更新记录

### 多设备路由
- `agent.py`：`/play` 接口新增 `device_id` 参数，支持按请求来源路由到不同设备
- `connection.py`：拦截播放指令时携带 `device_id` 字段，实现"从哪个设备触发就推给哪个设备"
- 默认设备由环境变量 `DEVICE_ID` 控制

### Cube 设备播放修复
- `agent.py`：推流前后发送 `tts_bridge start/stop` 控制消息
- `connection.py`：bridge 连接收到控制消息后，向目标设备发送标准 TTS 协议帧（`sentence_start` / `stop`），使 Cube 进入播放模式

### LLM 响应拦截修复
- `connection.py`：流式输出时，若累积内容以 `{` 开头则暂缓送入 TTS 队列，避免 JSON 播放指令被设备念出来

### 歌词搜索优化（music.py）
- 新增 embedding 相似度搜索，用 `paraphrase-multilingual-MiniLM-L12-v2` 模型做语义匹配
- 搜索顺序：精确匹配 → embedding 模糊匹配 → ncm-cli 在线搜索
