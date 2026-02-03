"""Pydantic数据模型定义"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SubtitleEntry(BaseModel):
    """字幕条目"""
    index: int
    start_time: float  # 秒
    end_time: float    # 秒
    text: str


class Section(BaseModel):
    """讲义小节"""
    id: int
    title: str
    start_time: float  # 秒
    end_time: float    # 秒
    content: str       # Markdown格式内容
    summary: str       # 小节摘要


class LectureMetadata(BaseModel):
    """讲义元数据"""
    video_file: str
    duration: float    # 秒
    created_at: datetime


class Lecture(BaseModel):
    """完整讲义"""
    title: str
    sections: List[Section]
    metadata: LectureMetadata


class WordTimestamp(BaseModel):
    """单词级时间戳"""
    word: str
    start_time: float
    end_time: float


class TranscriptionResult(BaseModel):
    """语音识别结果"""
    text: str  # 带标点的完整文本
    words: List[WordTimestamp]  # 词级时间戳（可能不带标点）
    duration: float


class ProcessingStage(BaseModel):
    """处理阶段状态"""
    name: str
    status: str  # pending, in_progress, completed, failed
    progress: Optional[int] = None
    message: Optional[str] = None


class ProcessingProgress(BaseModel):
    """处理进度"""
    task_id: str
    stage: str
    progress: int
    message: str
    stages: List[ProcessingStage]


class VideoProcessRequest(BaseModel):
    """视频处理请求"""
    video_path: str
    hotwords: Optional[List[str]] = None  # 用户自定义热词列表


class VideoProcessResponse(BaseModel):
    """视频处理响应"""
    task_id: str
    status: str
    message: str


class ExportRequest(BaseModel):
    """导出请求"""
    lecture_path: str
    format: str  # markdown 或 word


class ExportResponse(BaseModel):
    """导出响应"""
    file_path: str
    file_name: str


class HistoryItem(BaseModel):
    """历史记录项"""
    id: str  # 任务ID
    video_name: str  # 视频文件名
    video_path: str  # 视频文件路径
    output_dir: str  # 输出目录
    srt_path: str  # 字幕文件路径
    lecture_path: str  # 讲义文件路径
    duration: float  # 视频时长（秒）
    created_at: datetime  # 创建时间
    lecture_title: Optional[str] = None  # 讲义标题


class HistoryList(BaseModel):
    """历史记录列表"""
    items: List[HistoryItem]
    total: int


class StageInfo(BaseModel):
    """阶段信息"""
    stage_id: int
    stage_name: str
    stage_label: str
    status: str  # pending, in_progress, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_file: Optional[str] = None
    error: Optional[str] = None


class PipelineState(BaseModel):
    """处理流程状态"""
    task_id: str
    video_name: str
    video_path: str
    output_dir: str
    created_at: datetime
    updated_at: datetime
    duration: Optional[float] = None
    stages: List[StageInfo]
    hotwords: Optional[List[str]] = None
    metadata: Optional[dict] = None


class ReprocessRequest(BaseModel):
    """重新处理请求"""
    start_stage: str  # 起始阶段名称
    hotwords: Optional[List[str]] = None  # 可选：重新指定热词
