#!/bin/bash
# AvatarLive run script: mock LLM + FlashHead WebRTC service.
#
# Usage:
#   bash scripts/start_avatar_live.sh                 # use config/chat_flashhead_edge_tts.yaml
#   bash scripts/start_avatar_live.sh --config path  # custom config
#
# Requires a conda/venv python with the project deps; set PYTHON env or
# it falls back to `python`. Requires ssl_certs/localhost.{crt,key} (see
# scripts/create_ssl_certs.sh) and models downloaded (scripts/download_models.py).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIG="${CONFIG:-config/chat_flashhead_edge_tts.yaml}"
[ $# -ge 1 ] && CONFIG="$1"
PYTHON="${PYTHON:-python}"

# 1. Ensure mock LLM (OpenAI-compatible echo endpoint on :11434) is running.
if ! pgrep -f "[m]ock_llm.py" > /dev/null 2>&1; then
    echo "Starting mock LLM..."
    setsid nohup "$PYTHON" mock_llm.py > mock_llm.log 2>&1 < /dev/null &
    sleep 2
else
    echo "mock LLM already running"
fi

# 2. Start the FlashHead WebRTC service.
echo "Starting AvatarLive with: $CONFIG"
pkill -f "[s]rc/demo.py --config" 2>/dev/null
sleep 1
setsid nohup "$PYTHON" src/demo.py --config "$CONFIG" > oac_run.log 2>&1 < /dev/null &
echo "AvatarLive started. Log: oac_run.log | port: 8282 (see config)"
