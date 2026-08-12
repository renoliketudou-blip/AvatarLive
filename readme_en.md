# AvatarLive

Real-time digital-human streaming framework built on **SoulX-FlashHead**
(diffusion model) with WebRTC low-latency talking-head video.

Upload a photo → type / speak / upload audio → the digital human talks live.

## Highlights

- **Real-time talking head**: FlashHead Lite streaming inference, 25 FPS output, ~2× realtime on a single GPU
- **Three driving interfaces**:
  - **Text**: WebUI textbox / `POST /api/speak {"text": "..."}`
  - **Voice**: WebRTC microphone (real-time dialogue) / `POST /api/play` (WAV/MP3 bytes, lip-synced original voice)
  - **Avatar**: `POST /api/avatar` image upload → **hot-swap the digital human's face** (applies to all live sessions instantly)
- **Zero API keys**: default `mock LLM (echo) + edge-tts + FlashHead` works out of the box; swap in any OpenAI-compatible LLM later
- **Self-contained repo**: FlashHead engine, SileroVAD and WebUI are vendored — **no submodules**, clone and run

## Quick start

```bash
git clone git@github.com:renoliketudou-blip/AvatarLive.git
cd AvatarLive
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e .
uv run scripts/download_models.py --handler flashhead
bash scripts/create_ssl_certs.sh
bash scripts/start_avatar_live.sh
```
Open `https://<server>:8282/` and talk.

```bash
# Hot-swap the avatar
curl -sk -X POST https://<IP>:8282/api/avatar -F "file=@my_face.jpg"

# Make the digital human speak (broadcast to all sessions)
curl -sk -X POST https://<IP>:8282/api/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, I am your digital human assistant."}'

# Drive with an audio file (raw audio bytes, lip-synced original voice)
curl -sk -X POST https://<IP>:8282/api/play \
  -H "Content-Type: audio/mpeg" --data-binary @speech.mp3
```

## Docs

- [中文 README](README.md)
- [Optimizations & tuning notes](docs/OPTIMIZATIONS.md)
- [Deployment guide](docs/DEPLOYMENT.md)

## License & attribution

Forked from [OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat)
(Apache 2.0, commit `8b7b3b4`). Vendored components credited in [NOTICE](NOTICE).
Repo license: Apache 2.0.
