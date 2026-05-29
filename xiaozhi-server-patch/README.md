# xiaozhi-server-patch

这个目录包含了对 [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) 的修改，用于支持 **Bridge 推流** 功能。

---

## 我们增加了什么

### 核心功能：Bridge WebSocket 推流

允许一个外部程序（bridge 客户端）通过 WebSocket 连接到服务器，直接向已连接的小智设备推送 Opus 音频帧，绕过 ASR/LLM 流程，让设备直接播放指定音频（例如音乐片段）。

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/api/trigger_handler.py` | 新增 HTTP POST `/trigger` 接口，用于触发设备播放指定歌曲（通过 LLM 插件流程） |

### 修改文件

| 文件 | 改动内容 |
|------|---------|
| `core/websocket_server.py` | 在 `__init__` 中新增 `self.connections = {}` 字典，维护 device_id → ConnectionHandler 的映射 |
| `core/connection.py` | 1. 新增 `self.is_bridge` 和 `self.target_device` 字段；2. 设备连接时注册到 `server.connections`，断开时自动移除；3. 收到二进制帧时，若是 bridge 连接则转发给目标设备，否则走正常 ASR 流程 |
| `core/handle/helloHandle.py` | `handleHelloMessage` 中读取 `bridge` 和 `target_device` 字段，设置到 conn 上；若是 bridge 连接，从 `connections` 字典中移除自身（防止覆盖真实设备） |
| `core/http_server.py` | 1. 构造函数接收 `ws_server` 参数；2. 注册 `/trigger` 路由 |
| `app.py` | 创建 `SimpleHttpServer` 时传入 `ws_server`，使 HTTP 服务能访问已连接设备列表 |

---

## 为什么要这么做

小智设备通过 WebSocket 与服务器保持长连接，正常流程是：

```
设备麦克风 → Opus 音频帧 → 服务器 ASR → LLM → TTS → 设备播放
```

我们想实现的功能：检测到用户说出某首歌的歌词片段时，直接让设备播放那首歌的对应段落。

直接向服务器 WebSocket 推送 Opus 帧不起作用，因为服务器会把它当成 ASR 输入处理。

**解决方案：Bridge 连接模式**

bridge 客户端以特殊身份连接：
- 发送 `hello` 消息时携带 `"bridge": true` 和 `"target_device": "<设备ID>"`
- 服务器识别后，将该连接的所有二进制帧直接转发到目标设备的 WebSocket
- 目标设备收到 Opus 帧后直接播放，完全绕过 ASR/LLM

```
bridge客户端                     服务器                      小智设备
    |                              |                              |
    |  hello (bridge=true,         |                              |
    |         target_device=X)     |                              |
    |----------------------------->|                              |
    |                              |  hello (session_id)          |
    |<-----------------------------|                              |
    |                              |                              |
    |  Opus frame (binary)         |                              |
    |----------------------------->|  forward Opus frame          |
    |                              |----------------------------->|
    |                              |                              | 播放音频
```

---

## 怎么使用

### 1. 将修改后的文件覆盖到 xiaozhi-esp32-server 对应目录

```
xiaozhi-server-patch/
├── app.py                      → app.py
├── core/
│   ├── websocket_server.py     → core/websocket_server.py
│   ├── connection.py           → core/connection.py
│   ├── handle/
│   │   └── helloHandle.py      → core/handle/helloHandle.py
│   ├── http_server.py          → core/http_server.py
│   └── api/
│       └── trigger_handler.py  → core/api/trigger_handler.py (新文件)
```

### 2. Bridge 客户端连接协议

Hello 消息格式（在握手阶段发送）：

```json
{
  "type": "hello",
  "version": 1,
  "transport": "websocket",
  "bridge": true,
  "target_device": "DF:3F:F1:7A:6A:10",
  "audio_params": {
    "format": "opus",
    "sample_rate": 16000,
    "channels": 1,
    "frame_duration": 60
  }
}
```

之后直接发送原始 Opus 二进制帧即可，服务器会转发给目标设备。

### 3. `/trigger` HTTP 接口（可选）

通过 LLM 插件流程触发设备播放音乐：

```
POST http://<server>:8003/trigger
Authorization: Bearer <auth_key>
Content-Type: application/json

{
  "device_id": "DF:3F:F1:7A:6A:10",
  "song_name": "七里香"
}
```

---

## 配套的 bridge 客户端

见本仓库根目录的 `agent.py`，实现了：
1. 通过 ncm-cli 搜索歌词，定位歌曲片段的时间戳
2. 用 yt-dlp + ffmpeg 下载音频并转为 PCM 16kHz mono
3. 用 opuslib 编码为 Opus 帧并缓存
4. 以 bridge 模式连接服务器，推送 Opus 帧到指定设备
