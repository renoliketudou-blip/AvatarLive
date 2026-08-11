# AvatarLive 部署指南

## 目录
1. [单机部署（GPU）](#1-单机部署gpu)
2. [HTTPS 与证书](#2-https-与证书)
3. [公网 WebRTC：TURN 配置](#3-公网-webrtc-turn-配置)
4. [云主机 / 算力容器部署要点](#4-云主机--算力容器部署要点)
5. [Docker 部署](#5-docker-部署)
6. [模型离线下载](#6-模型离线下载)

---

## 1. 单机部署（GPU）

前置：NVIDIA GPU、Python 3.10/3.11、CUDA 12.x。

```bash
git clone git@github.com:renoliketudou-blip/AvatarLive.git
cd AvatarLive

uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e .

# 下载模型（FlashHead Lite + wav2vec2 + SenseVoice）
uv run scripts/download_models.py --handler flashhead

# 自签证书
bash scripts/create_ssl_certs.sh

# 启动（默认零 key 演示）
bash scripts/start_avatar_live.sh
```

验证：
```bash
curl -sk -o /dev/null -w "%{http_code}\n" https://127.0.0.1:8282/    # 307（重定向到 UI）
uv run python scripts/test_webrtc_client.py                          # WebRTC 自测，应收到视频帧
```

> 国内网络：模型走 HF/ModelScope 镜像，安装 flash-attn 失败属正常（本仓库已 `SKIP_PKGS` 跳过，走 SDPA，2× 实时够用）。

## 2. HTTPS 与证书

服务默认 HTTPS。`scripts/create_ssl_certs.sh` 生成自签 `ssl_certs/localhost.crt|key`。
- 浏览器首次访问会警告「不受信任」，点「继续访问」即可
- 自签证书不影响 WebRTC 媒体（RTC 走非 HTTPS 的 TURN 中继）
- 生产环境建议换正式证书（把 `.crt/.key` 放到 `ssl_certs/`，路径已在 config 里）

## 3. 公网 WebRTC：TURN 配置

**浏览器从公网连接必须配 TURN**（尤其服务器在纯 TCP 内网 / 只开放少量端口时）。

```bash
# 1) 启动 coturn（默认配置在 coturn-data/turnserver.conf）
bash scripts/setup_coturn.sh

# 2) 修改 config 里的 RtcClient.turn_config，填你的公网 IP 和 coturn 账号
RtcClient:
  turn_config:
    turn_provider: "turn_server"
    urls: ["turn:YOUR_PUBLIC_IP:3478?transport=tcp", "turns:YOUR_PUBLIC_IP:5349"]
    username: "username"
    credential: "password"
```

要点：
- **`?transport=tcp`** 很关键：很多云平台只转发 TCP 不转发 UDP，加了它 TURN 就能走 TCP 中继
- 媒体中继端口范围 `49152-65535` 需在防火墙放行（或收紧到更小范围）
- 自测客户端可用环境变量指定 TURN：
  ```bash
  RTC_TURN_URL="turn:IP:3478?transport=tcp" RTC_TURN_USER=username RTC_TURN_PASS=password \
    uv run python scripts/test_webrtc_client.py
  ```

## 4. 云主机 / 算力容器部署要点

以优云智算类 GPU 容器为例：

1. **端口**：控制台开放 `8282`（HTTPS/API）和 `3478`、`49152-65535`（TURN 媒体）。只开放了 SSH 的容器需要平台端口映射。
2. **模型**：容器常有预置模型目录（如 `/workspace/.../models`）。用软链复用，避免重复下载 13GB：
   ```bash
   ln -s /path/to/existing/models models
   ```
3. **后台常驻**：SSH 断开会杀进程，必须用 `setsid nohup` 或 systemd。仓库已提供 `scripts/start_avatar_live.sh`（内部就是 `setsid nohup`）。
4. **示例命令**（优云智算 4090 容器）：
   ```bash
   conda activate oac   # 或你自己的 python 环境
   export PYTHON=/path/to/python
   bash scripts/start_avatar_live.sh
   ```

## 5. Docker 部署

```bash
# 构建（基于仓库 Dockerfile，已裁剪为 FlashHead 专精）
docker build -t avatarlive .

# 运行（需挂载 models 和 ssl_certs，映射 8282 + TURN 端口）
docker run -d --gpus all -p 8282:8282 -p 3478:3478 -p 49152-65535:49152-65535 \
  -v $PWD/models:/app/models \
  -v $PWD/ssl_certs:/app/ssl_certs \
  --name avatarlive avatarlive
```

> 镜像构建细节与优云智算社区镜像上传流程：见 `docs/YOUDIAN_IMAGE.md`。

## 6. 模型离线下载

```bash
# 全部 FlashHead 相关模型
uv run scripts/download_models.py --handler flashhead

# 只下 SenseVoice（ASR）
uv run scripts/download_models.py --handler sensevoice
```

模型放 `models/` 下，对应 config 里的 `ckpt_dir` / `wav2vec_dir` / `model_name`：
- `models/SoulX-FlashHead-1_3B`（Lite）
- `models/wav2vec2-base-960h`
- `models/iic/SenseVoiceSmall`

> 仓库 `.gitignore` 已排除 `models/`，不会提交大文件。
