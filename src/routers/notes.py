"""閃念筆記 API — Append-only Markdown 存儲"""
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

import config

NOTES_DIR = config.NOTES_DIR


class NoteBody(BaseModel):
    quote: str = ""
    content: str
    juan: int = 1


def _today_file() -> Path:
    """返回今日筆記文件路徑"""
    return NOTES_DIR / f"{datetime.now().strftime('%Y-%m-%d')}-ReadingLog.md"


def _parse_notes(filepath: Path) -> list[dict]:
    """解析 Markdown 筆記文件，返回筆記列表（最新在前）"""
    if not filepath.exists():
        return []
    text = filepath.read_text(encoding="utf-8")
    notes = []
    blocks = text.split("---\n")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        note = {"time": "", "quote": "", "content": "", "sutra_id": "", "sutra_title": "", "juan": 0}
        lines = block.split("\n")
        for line in lines:
            if line.startswith("### 🕒"):
                # ### 🕒 10:05 | T0235 金剛般若波羅蜜經 · 卷1
                parts = line.replace("### 🕒 ", "").split(" | ", 1)
                note["time"] = parts[0].strip() if parts else ""
                if len(parts) > 1:
                    note["sutra_title"] = parts[1].strip()
            elif line.startswith("> "):
                quote_text = line[2:].strip()
                if note["quote"]:
                    note["quote"] += "\n" + quote_text
                else:
                    note["quote"] = quote_text
            elif line.startswith("📝 **感悟**："):
                note["content"] = line.replace("📝 **感悟**：", "").strip()
            elif line.startswith("📝 "):
                note["content"] = line[2:].strip()
        if note["content"] or note["quote"]:
            notes.append(note)
    notes.reverse()  # 最新在前
    return notes


@router.get("/api/notes/{sutra_id}")
async def get_notes(sutra_id: str):
    """獲取今日筆記"""
    filepath = _today_file()
    all_notes = _parse_notes(filepath)
    # 過濾當前經文的筆記（可選：也可以返回全部）
    filtered = [n for n in all_notes if sutra_id in n.get("sutra_title", "")]
    # 如果沒有過濾結果，返回全部今日筆記
    return {"notes": filtered if filtered else all_notes}


@router.post("/api/notes/{sutra_id}")
async def save_note(sutra_id: str, body: NoteBody, request: Request):
    """追加一條筆記"""
    now = datetime.now()
    filepath = _today_file()

    # 優先從運行中的導航索引獲取真實經名，前端漏傳 title 時也能正確保存。
    sutra_title = request.query_params.get("title", "").strip()
    if not sutra_title:
        nav = getattr(request.app.state, "nav", None)
        if nav is not None:
            sutra_title = nav.get_sutra_title(sutra_id) or ""
    if not sutra_title:
        sutra_title = sutra_id

    # 構造 Markdown 條目
    entry_lines = [
        f"### 🕒 {now.strftime('%H:%M')} | {sutra_id} {sutra_title} · 卷{body.juan}",
        "",
    ]
    if body.quote:
        for qline in body.quote.split("\n"):
            entry_lines.append(f"> {qline}")
        entry_lines.append("")
    entry_lines.append(f"📝 **感悟**：{body.content}")
    entry_lines.append("")
    entry_lines.append("---")
    entry_lines.append("")

    entry = "\n".join(entry_lines)

    # 確保筆記目錄存在
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    # Append 到文件
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(entry)

    return {"ok": True, "time": now.strftime("%H:%M")}
