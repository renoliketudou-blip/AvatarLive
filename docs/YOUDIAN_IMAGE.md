# 优云智算社区镜像构建指南（后续阶段）

> ⚠️ 本文描述构建与上传流程，**镜像上传按用户约定在后续阶段执行**（M7 之后）。
> 本仓库已包含可构建的 `Dockerfile` 与 `docker-compose.yml`。

## 1. 本地构建（验证通过）

```bash
# 构建 FlashHead 专精镜像
docker build -t avatarlive:latest .

# 验证容器能启动（挂载模型 + 证书）
docker run -d --gpus all -p 8282:8282 -p 3478:3478 -p 49152-65535:49152-65535 \
  -v $PWD/models:/app/models \
  -v $PWD/ssl_certs:/app/ssl_certs \
  --name avatarlive avatarlive:latest
```

## 2. 社区镜像要点

优云智算（及同类 GPU 算力平台）社区镜像 = 预置好环境的容器镜像，用户拉取即跑。

- **CUDA 基座**：`nvidia/cuda:12.x-devel-ubuntu22.04`（FlashHead Lite 需 CUDA 12.x）
- **Python**：3.11 + `uv` + PyTorch 2.x（含 cu12x 轮子）
- **预置模型**：FlashHead Lite（~13GB）、wav2vec2、SenseVoice 直接 bake 进镜像，用户免下载 —— 这也是镜像最大的体积来源
- **entrypoint**：镜像启动即跑 `scripts/start_avatar_live.sh`（mock LLM + 服务）
- **端口**：`8282`（HTTPS/API）、`3478/5349`（TURN）、`49152-65535`（媒体中继）
- **证书**：首次启动自动生成自签证书（或 bake 一个占位证书）

## 3. Dockerfile 思路（骨架）

```dockerfile
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04
RUN apt-get update && apt-get install -y python3.11 python3-pip git ffmpeg libgl1 && \
    pip install uv
COPY . /app
WORKDIR /app
RUN uv venv --python 3.11 && uv pip install -e .
# 模型 bake 进镜像（或运行时挂载）
COPY models/ /app/models/
COPY ssl_certs/ /app/ssl_certs/
EXPOSE 8282 3478 5349 49152-65535
CMD ["bash", "scripts/start_avatar_live.sh"]
```

## 4. 上传 / 审核流程

1. 平台控制台 → 「镜像管理」→「发布社区镜像」
2. 填元信息：镜像名、描述、GPU 需求（≥16GB）、端口说明
3. 平台审核（通常需提供「开箱即用」验证截图/日志）
4. 审核通过后用户端一键创建实例

## 5. 注意事项

- **冷启动**：镜像首次启动加载模型 ~10-15s，属于正常；可用预热脚本预跑一次生成缓存
- **TURN**：社区实例的公网 NAT 通常只转发 TCP —— 镜像内置 coturn + `?transport=tcp` 配置，实例启动后把 `config/*.yaml` 里的 `turn_config` 地址改成实例的公网 IP 即可
- **隐私**：镜像不 bake 任何真人照片，默认 `girl.png`
