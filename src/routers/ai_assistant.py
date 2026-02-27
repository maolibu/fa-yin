"""
AI 释义 API — 统一多 LLM 提供商（OpenAI 兼容格式）

用法: POST /api/ai/chat
Body: {"text": "如是我聞...", "mode": "translate", "provider": "deepseek", "api_key": "sk-..."}
返回: SSE text/event-stream
"""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import config

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# ─── 预置 System Prompts ─────────────────────────────────────

SYSTEM_PROMPTS = {
    "translate": (
        "你是一位精通佛学的翻译专家。"
        "请将用户提供的佛经原文翻译为现代白话文，保持原意不增不减。"
        "遇到专有名词（如般若、涅槃、菩提等）保留原词并在括号中简要注释。"
        "翻译应当通顺流畅、信达雅兼备。"
    ),
    "explain": (
        "你是一位佛学辞典编纂专家。"
        "请对用户提供的佛学名词或经文片段进行详细释义，包括：\n"
        "1. 词义解释（梵文原义、汉译含义）\n"
        "2. 在佛法中的意涵\n"
        "3. 相关经典出处\n"
        "回答应当严谨准确，通俗易懂。"
    ),
    "ask": (
        "你是一位博学的佛学研究助手。"
        "请根据用户选中的经文内容和提出的问题，给出详细、准确的回答。"
        "回答应引经据典，同时用现代语言表述，适合佛学初学者理解。"
    ),
}


# ─── 请求模型 ─────────────────────────────────────────────────

class AIChatRequest(BaseModel):
    text: str = Field("", max_length=5000, description="选中的经文内容（自由问答模式可空）")
    mode: str = Field("translate", description="translate / explain / ask")
    provider: str = Field("deepseek", description="提供商 ID")
    api_key: str = Field("", description="用户的 API Key（可选）")
    question: str = Field("", description="自由问答时的用户问题")
    sutra_title: str = Field("", description="当前经文标题（上下文）")
    custom_url: str = Field("", description="自定义提供商的 API 地址")
    custom_model: str = Field("", description="自定义提供商的模型名")


# ─── 提供商列表 API ───────────────────────────────────────────

@router.get("/providers")
async def list_providers():
    """返回可用的 AI 提供商列表（不含 API Key）"""
    providers = []
    for pid, info in config.AI_PROVIDERS.items():
        providers.append({
            "id": pid,
            "name": info["name"],
            "default_model": info["default_model"],
            "no_key": info.get("no_key", False),
            "has_server_key": bool(config.AI_DEFAULT_KEY) and pid == config.AI_DEFAULT_PROVIDER,
        })
    return {"providers": providers, "default": config.AI_DEFAULT_PROVIDER}


# ─── 流式聊天 API ────────────────────────────────────────────

@router.post("/chat")
async def ai_chat(req: AIChatRequest):
    """调用 LLM 并以 SSE 流式返回结果"""

    # 获取提供商配置
    provider_cfg = config.AI_PROVIDERS.get(req.provider)
    if not provider_cfg:
        return StreamingResponse(
            _error_stream(f"未知的提供商: {req.provider}"),
            media_type="text/event-stream",
        )

    # 自定义提供商：用用户填写的 URL 和 Model 覆盖
    if req.provider == "custom":
        if not req.custom_url.strip():
            return StreamingResponse(
                _error_stream("请在设置面板中填入自定义 API 地址"),
                media_type="text/event-stream",
            )
        provider_cfg = dict(provider_cfg)  # 复制一份避免修改全局配置
        provider_cfg["base_url"] = req.custom_url.strip()
        provider_cfg["default_model"] = req.custom_model.strip() or "default"

    # 确定 API Key
    api_key = req.api_key.strip() if req.api_key else ""
    if not api_key:
        # 回退到服务端默认 key（仅限匹配的提供商）
        if req.provider == config.AI_DEFAULT_PROVIDER and config.AI_DEFAULT_KEY:
            api_key = config.AI_DEFAULT_KEY
        elif provider_cfg.get("no_key"):
            api_key = "ollama"  # Ollama 不需要真实 key，但 openai 包要求非空
        else:
            return StreamingResponse(
                _error_stream("请在设置面板中填入 API Key"),
                media_type="text/event-stream",
            )

    # 校验：翻译和释义必须有经文文本
    if req.mode in ("translate", "explain") and not req.text.strip():
        return StreamingResponse(
            _error_stream("请先在经文中选中文字"),
            media_type="text/event-stream",
        )

    # 校验：自由问答至少要有经文或问题
    if req.mode == "ask" and not req.text.strip() and not req.question.strip():
        return StreamingResponse(
            _error_stream("请输入问题，或先选中经文"),
            media_type="text/event-stream",
        )

    # 构建消息
    system_prompt = SYSTEM_PROMPTS.get(req.mode, SYSTEM_PROMPTS["translate"])
    if req.sutra_title:
        system_prompt += f"\n\n当前阅读的经文：《{req.sutra_title}》"

    if req.mode == "ask":
        parts = []
        if req.text.strip():
            parts.append(f"经文内容：\n{req.text}")
        if req.question.strip():
            parts.append(f"我的问题：{req.question}")
        user_msg = "\n\n".join(parts)
    else:
        user_msg = req.text

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    return StreamingResponse(
        _stream_chat(provider_cfg, api_key, messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_chat(provider_cfg, api_key, messages):
    """使用 openai 包进行流式调用，yield SSE 格式"""
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=provider_cfg["base_url"],
            api_key=api_key,
        )

        stream = client.chat.completions.create(
            model=provider_cfg["default_model"],
            messages=messages,
            stream=True,
            max_tokens=2000,
            temperature=0.7,
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    except ImportError:
        yield f"data: {json.dumps({'error': '服务端未安装 openai 包，请运行: pip install openai'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        log.error(f"AI 调用失败: {e}")
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


async def _error_stream(msg):
    """生成错误 SSE 流"""
    yield f"data: {json.dumps({'error': msg}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
