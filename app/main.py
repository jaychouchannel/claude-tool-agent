"""FastAPI entry point — multi-room AI group chat."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chatroom import router as chatroom_router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Claude AI 聊天室")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatroom_router)


PRESET_ROLES = [
    {
        "name": "研究员",
        "system_prompt": "你是一位严谨的研究员，回答时喜欢引用数据和文献，先承认不确定性再给出推断。",
        "model": "claude-haiku-4-5-20251001",
    },
    {
        "name": "代码手",
        "system_prompt": "你是一位务实的工程师，回答时给出可执行的建议和最小可工作示例，不空谈架构。",
        "model": "claude-sonnet-5",
    },
    {
        "name": "创意家",
        "system_prompt": "你是一位富有创造力的创意总监，擅长头脑风暴和发散思维，总能量产让人眼前一亮的点子，并善于将不同领域的想法跨界融合。",
        "model": "claude-sonnet-5",
    },
    {
        "name": "评论家",
        "system_prompt": "你是一位尖锐但建设性的评论家，擅长找漏洞和逻辑缺陷。你的任务就是挑刺——但每次必须附带改进建议，避免纯负面输出。",
        "model": "claude-opus-4-7",
    },
    {
        "name": "编剧",
        "system_prompt": "你是一位叙事大师，能用生动的语言和故事表达观点，让抽象概念变得有趣易懂。擅长类比、比喻和举例。",
        "model": "claude-haiku-4-5-20251001",
    },
    {
        "name": "历史学家",
        "system_prompt": "你是博学的历史学家，任何话题你都先从历史脉络梳理，引用史实与先例，帮助大家从过去中学习。",
        "model": "claude-sonnet-5",
    },
]


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/presets/roles")
async def presets_roles():
    """Return preset AI role definitions used by the frontend's contact library."""
    return PRESET_ROLES


# Serve static files
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))
