"""WebSocket路由 - 实时进度推送"""
import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# 存储活动的WebSocket连接
active_connections: Dict[str, Set[WebSocket]] = {}


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, task_id: str):
        """建立连接"""
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        logger.info(f"WebSocket连接建立: task_id={task_id}")
    
    def disconnect(self, websocket: WebSocket, task_id: str):
        """断开连接"""
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        logger.info(f"WebSocket连接断开: task_id={task_id}")
    
    async def send_to_task(self, task_id: str, message: dict):
        """发送消息到指定任务的所有连接"""
        if task_id not in self.active_connections:
            return
        
        disconnected = set()
        for websocket in self.active_connections[task_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"发送WebSocket消息失败: {e}")
                disconnected.add(websocket)
        
        # 清理断开的连接
        for ws in disconnected:
            self.active_connections[task_id].discard(ws)


# 全局连接管理器
manager = ConnectionManager()


# 处理阶段定义（与后端video.py处理流程保持一致）
STAGES = [
    {"name": "extract_audio", "label": "提取音频"},
    {"name": "asr", "label": "语音识别"},
    {"name": "text_correct", "label": "文本纠错"},
    {"name": "align", "label": "时间对齐"},
    {"name": "subtitle", "label": "生成字幕"},
    {"name": "section_split", "label": "划分小节"},
    {"name": "lecture_gen", "label": "生成讲义"},
]


def build_progress_message(
    task_id: str,
    current_stage: str,
    progress: int,
    message: str
) -> dict:
    """
    构建进度消息
    
    Args:
        task_id: 任务ID
        current_stage: 当前阶段
        progress: 当前阶段进度 (0-100)
        message: 进度消息
        
    Returns:
        进度消息字典
    """
    stages = []
    current_found = False
    
    for stage in STAGES:
        if stage["name"] == current_stage:
            current_found = True
            stages.append({
                "name": stage["name"],
                "label": stage["label"],
                "status": "in_progress",
                "progress": progress
            })
        elif not current_found:
            stages.append({
                "name": stage["name"],
                "label": stage["label"],
                "status": "completed",
                "progress": 100
            })
        else:
            stages.append({
                "name": stage["name"],
                "label": stage["label"],
                "status": "pending",
                "progress": 0
            })
    
    # 处理完成或错误状态
    if current_stage == "done":
        for stage in stages:
            stage["status"] = "completed"
            stage["progress"] = 100
    elif current_stage == "error":
        for stage in stages:
            if stage["status"] == "in_progress":
                stage["status"] = "failed"
    
    return {
        "task_id": task_id,
        "stage": current_stage,
        "progress": progress,
        "message": message,
        "stages": stages
    }


async def send_progress(
    task_id: str,
    stage: str,
    progress: int,
    message: str
):
    """
    发送进度更新
    
    Args:
        task_id: 任务ID
        stage: 当前阶段
        progress: 进度 (0-100)
        message: 进度消息
    """
    progress_msg = build_progress_message(task_id, stage, progress, message)
    await manager.send_to_task(task_id, progress_msg)


@router.websocket("/progress/{task_id}")
async def websocket_progress(websocket: WebSocket, task_id: str):
    """
    WebSocket连接端点，用于接收处理进度更新
    
    Args:
        websocket: WebSocket连接
        task_id: 任务ID
    """
    await manager.connect(websocket, task_id)
    
    try:
        # 发送初始连接成功消息
        await websocket.send_json({
            "type": "connected",
            "task_id": task_id,
            "message": "连接成功，等待处理进度..."
        })
        
        # 保持连接，等待断开
        while True:
            try:
                # 接收客户端消息（心跳等）
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                # 处理心跳
                if data == "ping":
                    await websocket.send_text("pong")
                    
            except asyncio.TimeoutError:
                # 发送心跳检测
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        logger.info(f"客户端断开连接: task_id={task_id}")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
    finally:
        manager.disconnect(websocket, task_id)
