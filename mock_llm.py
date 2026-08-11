#!/usr/bin/env python3
"""本地 OpenAI 兼容 mock LLM（流式 SSE），监听 11434。
回声模式：把用户输入的文本原样返回，让数字人"念出来"用户的语音。"""
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json

app = FastAPI()


def get_echo(body) -> str:
    content = ""
    for m in body.get("messages", []):
        if m.get("role") == "user":
            content = m.get("content", "") or ""
    content = str(content).strip()
    if not content:
        content = "嗯，我听到了。"
    return content


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    stream = body.get("stream", False)
    model = body.get("model", "mock")
    req_id = "chatcmpl-mock-0001"
    content = get_echo(body)

    if not stream:
        return {
            "id": req_id, "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": len(content), "total_tokens": len(content)},
        }

    def gen():
        for i, ch in enumerate(content):
            last = (i == len(content) - 1)
            chunk = {
                "id": req_id, "object": "chat.completion.chunk", "model": model,
                "choices": [{"index": 0, "delta": {"content": ch}, "finish_reason": "stop" if last else None}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        usage = {
            "id": req_id, "object": "chat.completion.chunk", "model": model,
            "choices": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": len(content), "total_tokens": len(content)},
        }
        yield f"data: {json.dumps(usage, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=11434, log_level="warning")
