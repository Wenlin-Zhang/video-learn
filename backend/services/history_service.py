"""历史记录服务 - 管理已处理视频的历史记录"""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from models.schemas import HistoryItem, HistoryList

logger = logging.getLogger(__name__)


class HistoryService:
    """历史记录服务"""
    
    def __init__(self, history_file: Optional[str] = None):
        """
        初始化历史记录服务
        
        Args:
            history_file: 历史记录文件路径，默认为storage目录下的history.json
        """
        config = get_config()
        if history_file:
            self.history_file = Path(history_file)
        else:
            self.history_file = Path(config.storage.output_dir) / "history.json"
        
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self._history: List[HistoryItem] = []
        self._load()
        
        logger.info(f"历史记录服务初始化，文件: {self.history_file}")
    
    def _load(self) -> None:
        """从文件加载历史记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._history = [HistoryItem(**item) for item in data]
                logger.info(f"加载 {len(self._history)} 条历史记录")
            except Exception as e:
                logger.error(f"加载历史记录失败: {e}")
                self._history = []
        else:
            self._history = []
    
    def _save(self) -> None:
        """保存历史记录到文件"""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                data = [item.model_dump(mode="json") for item in self._history]
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"保存 {len(self._history)} 条历史记录")
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")
    
    def add(
        self,
        task_id: str,
        video_name: str,
        video_path: str,
        output_dir: str,
        srt_path: str,
        lecture_path: str,
        duration: float,
        lecture_title: Optional[str] = None
    ) -> HistoryItem:
        """
        添加历史记录
        
        Args:
            task_id: 任务ID
            video_name: 视频文件名
            video_path: 视频文件路径
            output_dir: 输出目录
            srt_path: 字幕文件路径
            lecture_path: 讲义文件路径
            duration: 视频时长
            lecture_title: 讲义标题
            
        Returns:
            新创建的历史记录项
        """
        item = HistoryItem(
            id=task_id,
            video_name=video_name,
            video_path=video_path,
            output_dir=output_dir,
            srt_path=srt_path,
            lecture_path=lecture_path,
            duration=duration,
            created_at=datetime.now(),
            lecture_title=lecture_title
        )
        
        # 检查是否已存在
        for i, existing in enumerate(self._history):
            if existing.id == task_id:
                self._history[i] = item
                self._save()
                logger.info(f"更新历史记录: {task_id}")
                return item
        
        self._history.insert(0, item)  # 新记录放在最前面
        self._save()
        logger.info(f"添加历史记录: {task_id} - {video_name}")
        return item
    
    def get(self, task_id: str) -> Optional[HistoryItem]:
        """
        获取单条历史记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            历史记录项，不存在则返回None
        """
        for item in self._history:
            if item.id == task_id:
                return item
        return None
    
    def list(self, limit: int = 50, offset: int = 0) -> HistoryList:
        """
        获取历史记录列表
        
        Args:
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            历史记录列表
        """
        total = len(self._history)
        items = self._history[offset:offset + limit]
        return HistoryList(items=items, total=total)
    
    def delete(self, task_id: str, delete_files: bool = True) -> bool:
        """
        删除历史记录
        
        Args:
            task_id: 任务ID
            delete_files: 是否同时删除文件
            
        Returns:
            是否删除成功
        """
        for i, item in enumerate(self._history):
            if item.id == task_id:
                if delete_files:
                    # 删除输出目录
                    output_dir = Path(item.output_dir)
                    if output_dir.exists():
                        try:
                            shutil.rmtree(output_dir)
                            logger.info(f"删除输出目录: {output_dir}")
                        except Exception as e:
                            logger.error(f"删除输出目录失败: {e}")
                    
                    # 删除视频文件（如果在上传目录中）
                    video_path = Path(item.video_path)
                    if video_path.exists() and "uploads" in str(video_path):
                        try:
                            video_path.unlink()
                            logger.info(f"删除视频文件: {video_path}")
                        except Exception as e:
                            logger.error(f"删除视频文件失败: {e}")
                
                del self._history[i]
                self._save()
                logger.info(f"删除历史记录: {task_id}")
                return True
        
        return False
    
    def exists(self, task_id: str) -> bool:
        """检查历史记录是否存在"""
        return any(item.id == task_id for item in self._history)
    
    def validate(self, task_id: str) -> bool:
        """
        验证历史记录对应的文件是否存在
        
        Args:
            task_id: 任务ID
            
        Returns:
            文件是否都存在
        """
        item = self.get(task_id)
        if not item:
            return False
        
        return (
            Path(item.srt_path).exists() and
            Path(item.lecture_path).exists()
        )


# 全局实例
_history_service: Optional[HistoryService] = None


def get_history_service() -> HistoryService:
    """获取历史记录服务实例"""
    global _history_service
    if _history_service is None:
        _history_service = HistoryService()
    return _history_service
