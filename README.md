<h1 align="center">AvatarLive</h1>

<p align="center">
<strong>实时数字人直播框架 —— 基于 SoulX-FlashHead 扩散模型，WebRTC 低延迟说话视频。</strong>
</p>

<p align="center">
上传一张照片 → 输入文字 / 说话 / 上传音频 → 数字人实时开口说话
</p>

---

## ✨ 核心特性

- **实时说话头**：SoulX-FlashHead Lite 扩散模型流式推理，25 FPS 视频输出，推理 ~2× 实时（单卡即可跑）
- **三种驱动接口**：
  - **文字**：WebUI 文本框 / `POST /api/speak {"text": "..."}`
  - **语音**：WebRTC 麦克风实时对话 / `POST /api/speak`（WAV/MP3 字节）
  - **形象**：`POST /api/avatar` 上传图片 → **热换数字人形象**（所有已连会话即时生效）
- **零 API Key 开箱**：默认链路 `mock LLM（回声）+ edge-tts + FlashHead`，无需任何外部 key；支持随时换成真实 LLM（任意 OpenAI 兼容端点）
- **双工打断**：对话可随时打断，自动复位口型与待机
- **自包含仓库**：FlashHead 推理引擎、SileroVAD、WebUI 已 vendored，**无 submodule 依赖**，clone 即用

## 🏗️ 架构

AvatarLive 是 [OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat)（v0.6.0, commit `8b7b3b4`）的二次开发 fork，聚焦 FlashHead 专精：

```
浏览器 / WebRTC ──┬── 麦克风 ──▶ SenseVoice ASR ──▶ mock/真实 LLM ──┐
                  ├── 摄像头 ──┐                                    ├─▶ edge-tts ──▶ FlashHead 流式引擎 ──▶ 512×512 视频 + 音频
                  └── 文本框 ──┴──▶ LLM 文字通路 ───────────────────┘                        ▲
                                                                                           │
HTTP API ──▶ /api/avatar（图片上传热换形象）│ /api/speak（文字/音频广播）─────────────────┘
```

- **FlashHead 引擎**（`src/handlers/avatar/flashhead/`）—— 现成的实时流式引擎：滑动音频窗口、25 FPS 帧采集、静音待机微动、音画同步、双工打断。推理源码已 vendored（Apache 2.0，见 `NOTICE`）。
- **WebRTC 传输** —— 继承 OAC 的 gradio-webrtc + coturn（TURN）基础设施，公网 NAT 穿透开箱。

## 🚀 快速开始

### 环境要求
- Linux + NVIDIA GPU（≥16GB 显存，Lite 模型实测 ~6.2GB）
- Python 3.10 / 3.11、CUDA 12.x、PyTorch 2.x

### 安装
```bash
git clone git@github.com:renoliketudou-blip/AvatarLive.git
cd AvatarLive

# 1) 创建虚拟环境并安装依赖（跳过 flash-attn/xformers/mediapipe 编译，走 SDPA 回退）
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e .   # 或 uv run install.py --config config/chat_flashhead_edge_tts.yaml

# 2) 下载模型（FlashHead Lite ~13GB + wav2vec2 + SenseVoice）
uv run scripts/download_models.py --handler flashhead

# 3) 生成自签 HTTPS 证书（浏览器首次访问需信任）
bash scripts/create_ssl_certs.sh
```

### 启动（零 Key 演示模式）
```bash
bash scripts/start_avatar_live.sh            # mock LLM + 服务，端口 8282
```
浏览器打开 `https://<服务器IP>:8282/` → 文本/语音/上传形象，全部可用。

> 默认形象是官方示例 `girl.png`。用 `POST /api/avatar` 上传你自己的照片即可换形象（正脸、睁眼、嘴闭合的照片效果最好，见 [docs/OPTIMIZATIONS.md](docs/OPTIMIZATIONS.md)）。

### 启动（全闭环对话模式，需 LLM API）
```bash
# 编辑 config/chat_with_openai_compatible_bailian_cosyvoice_flashhead.yaml，
# 填入百炼/DeepSeek/任意 OpenAI 兼容 api_key 与 api_url
export DASHSCOPE_API_KEY="sk-xxx"
uv run src/demo.py --config config/chat_with_openai_compatible_bailian_cosyvoice_flashhead.yaml
```

## 🌐 HTTP API 参考

| 方法 | 路径 | 请求 | 说明 |
|---|---|---|---|
| POST | `/api/avatar` | multipart `file=<图片>` | 上传图片热换数字人形象（立即生效） |
| POST | `/api/speak` | JSON `{"text": "...", "voice": "zh-CN-XiaoxiaoNeural"}` | 文字 → edge-tts → 数字人说话（广播到所有已连会话） |
| POST | `/api/speak` | 原始音频字节（WAV 16-bit PCM / MP3） | 音频 → 数字人说话 |
| POST | `/webrtc/offer` | WebRTC SDP offer | WebRTC 建连（浏览器/客户端） |

```bash
# 换形象
curl -sk -X POST https://<IP>:8282/api/avatar -F "file=@my_face.jpg"

# 让数字人说一句话
curl -sk -X POST https://<IP>:8282/api/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "大家好，我是你的数字人助理"}'

# 用一段音频驱动
curl -sk -X POST https://<IP>:8282/api/speak \
  -H "Content-Type: audio/mpeg" --data-binary @speech.mp3
```

## 🔌 端口与公网访问

- **HTTPS WebUI / API**：`8282`（自签证书）
- **TURN**：coturn，`3478`(TCP)/`5349`(TLS)。公网浏览器访问必须配 TURN（尤其纯 TCP 网络），在 `config/*.yaml` 的 `RtcClient.turn_config` 填写你的服务器地址与账号，并运行 `bash scripts/setup_coturn.sh`。
- WebRTC 媒体走 TURN 中继端口范围 `49152-65535`（见 `coturn-data/turnserver.conf`）。

## 📋 已知限制与调优

- **口型幅度偏保守**：FlashHead 是扩散模型，动态幅度天然低于真实音视频对口型；待机时嘴保持闭合（参考图决定待机基线，`idle_noise_amplitude: 0.0`）
- **首帧延迟**：冷启动加载模型约 10-15s；触发→开口约 1s
- **TTS 网络依赖**：edge-tts 走微软在线服务（合成 2-6s）；如需本地化可换 CosyVoice（见规划）
- 完整调优心得见 **[docs/OPTIMIZATIONS.md](docs/OPTIMIZATIONS.md)**

## 📁 目录结构

```
config/                          # 运行配置（edge-tts 零 key 默认 / bailian 全闭环）
resource/avatar/flashhead/       # 默认形象 girl.png（换成你自己的照片）
src/handlers/avatar/flashhead/   # FlashHead 流式引擎（processor + handler + vendored 推理）
src/service/api_server.py        # HTTP API（形象上传 + 文字/音频广播）
scripts/                         # 启动 / 自测 / 模型下载 / 证书
docs/                            # 部署与调优文档
NOTICE                           # 上游项目与 vendored 组件署名
```

## 🧪 自测

```bash
# 1) 模块导入自检
uv run python scripts/selftest_import.py

# 2) WebRTC 连通自测（服务需已启动，本机跑）
uv run python scripts/test_webrtc_client.py
uv run python scripts/test_webrtc_speech.py /path/to/speech.wav
```

## ⚖️ 致谢与许可

本项目 fork 自 [OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat)（Apache 2.0, commit `8b7b3b4`），并 vendored 了以下开源组件（Apache 2.0 / MIT），完整署名见 **[NOTICE](NOTICE)**：
- [Soul-AILab/SoulX-FlashHead](https://github.com/Soul-AILab/SoulX-FlashHead)（推理引擎）
- [snakers4/silero-vad](https://github.com/snakers4/silero-vad)（VAD）
- [HumanAIGC-Engineering/OpenAvatarChat-WebUI](https://github.com/HumanAIGC-Engineering/OpenAvatarChat-WebUI)（WebUI）

[English](readme_en.md) | 仓库 LICENSE：Apache 2.0
