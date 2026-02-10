"""FastAPI应用入口"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import load_config
from routers import video, export, websocket
from services.history_service import get_history_service

# 创建日志目录
log_dir = Path("logs")
log_dir.mkdir(parents=True, exist_ok=True)

# 配置日志
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 创建根日志器
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(log_format))

# 文件处理器（自动轮转，最大10MB，保留5个备份）
file_handler = RotatingFileHandler(
    log_dir / "app.log",
    maxBytes=10*1024*1024,
    backupCount=5,
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(log_format))

# 添加处理器
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# 加载配置
config = load_config()

# 创建FastAPI应用
app = FastAPI(
    title="课程教学视频处理系统",
    description="处理教学视频，生成字幕和讲义",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(video.router, prefix="/api/video", tags=["视频处理"])
app.include_router(export.router, prefix="/api/export", tags=["导出"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])

# 挂载静态文件目录（用于访问生成的文件）
uploads_dir = Path(config.storage.upload_dir)
outputs_dir = Path(config.storage.output_dir)
uploads_dir.mkdir(parents=True, exist_ok=True)
outputs_dir.mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

# 启动时迁移旧数据 + 清理孤儿文件
history_service = get_history_service()
migrate_stats = history_service.migrate_legacy_data()
if migrate_stats["migrated"] > 0:
    logger.info(f"迁移旧数据: {migrate_stats['migrated']} 条记录")

naming_stats = history_service.migrate_naming_convention()
if naming_stats["renamed"] > 0:
    logger.info(f"重命名文件: {naming_stats['renamed']} 条记录")

cleanup_stats = history_service.cleanup_orphan_files()
if cleanup_stats["cleaned_uploads"] > 0 or cleanup_stats["cleaned_outputs"] > 0:
    logger.info(
        f"清理孤儿文件: uploads={cleanup_stats['cleaned_uploads']}, "
        f"outputs={cleanup_stats['cleaned_outputs']}, "
        f"释放 {cleanup_stats['freed_bytes'] / 1024 / 1024:.1f} MB"
    )


@app.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "message": "课程教学视频处理系统正在运行"}


@app.get("/api/config")
async def get_app_config():
    """获取应用配置（不包含敏感信息）"""
    return {
        "asr_model": config.asr.model,
        "aligner_model": config.asr.aligner_model,
        "llm_model": config.llm.model,
        "device": config.asr.device,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
