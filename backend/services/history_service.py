"""历史记录服务 - 管理已处理视频的历史记录"""
import json
import logging
import re
import shutil
import uuid as uuid_mod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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
                    
                    # 删除视频文件（仅当在上传目录中时）
                    video_path = Path(item.video_path)
                    if video_path.exists():
                        try:
                            upload_dir = Path(get_config().storage.upload_dir).resolve()
                            if video_path.resolve().is_relative_to(upload_dir):
                                video_path.unlink()
                                logger.info(f"删除视频文件: {video_path}")
                        except (ValueError, OSError) as e:
                            logger.error(f"删除视频文件失败: {e}")
                
                del self._history[i]
                self._save()
                logger.info(f"删除历史记录: {task_id}")
                return True
        
        return False
    
    def exists(self, task_id: str) -> bool:
        """检查历史记录是否存在"""
        return any(item.id == task_id for item in self._history)
    
    def find_by_original_name(self, filename: str) -> List[HistoryItem]:
        """
        按原始文件名搜索历史记录（去除 UUID 和扩展名后比较）
        
        Args:
            filename: 原始文件名（如 my_video.mp4）
            
        Returns:
            匹配的历史记录列表
        """
        target = self._strip_task_id(filename)
        results = []
        for item in self._history:
            if self._strip_task_id(item.video_name) == target:
                results.append(item)
        return results
    
    @staticmethod
    def _strip_task_id(filename: str) -> str:
        """从文件名中去除 UUID 后缀/前缀和扩展名，返回纯净名称"""
        stem = Path(filename).stem
        # 去除末尾 UUID 后缀
        cleaned = re.sub(
            r'_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
            '', stem, flags=re.IGNORECASE
        )
        # 兼容旧命名：去除开头 UUID 前缀
        cleaned = re.sub(
            r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_',
            '', cleaned, flags=re.IGNORECASE
        )
        return cleaned
    
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
    
    def migrate_legacy_data(self) -> Dict[str, int]:
        """
        将旧数据的 output 目录从 uploads/ 迁移到 outputs/
        
        Returns:
            迁移统计 {"migrated": N}
        """
        config = get_config()
        upload_dir = Path(config.storage.upload_dir).resolve()
        output_dir_root = Path(config.storage.output_dir).resolve()
        stats = {"migrated": 0}
        
        changed = False
        for item in self._history:
            item_output = Path(item.output_dir)
            try:
                # 检查 output_dir 是否在 upload_dir 内
                if not item_output.resolve().is_relative_to(upload_dir):
                    continue
            except (ValueError, OSError):
                continue
            
            new_output_dir = output_dir_root / item_output.name
            
            # 移动目录
            if item_output.exists():
                try:
                    shutil.move(str(item_output), str(new_output_dir))
                    logger.info(f"迁移输出目录: {item_output} -> {new_output_dir}")
                except Exception as e:
                    logger.error(f"迁移输出目录失败: {item_output} -> {e}")
                    continue
            
            # 更新路径（使用相对路径保持一致性）
            old_output_str = item.output_dir
            new_output_str = str(Path(config.storage.output_dir) / item_output.name)
            
            item.output_dir = new_output_str
            if item.srt_path.startswith(old_output_str):
                item.srt_path = item.srt_path.replace(old_output_str, new_output_str, 1)
            if item.lecture_path.startswith(old_output_str):
                item.lecture_path = item.lecture_path.replace(old_output_str, new_output_str, 1)
            
            stats["migrated"] += 1
            changed = True
        
        if changed:
            self._save()
        
        return stats
    
    def migrate_naming_convention(self) -> Dict[str, int]:
        """
        将旧命名 {task_id}_{名称} 迁移为新命名 {名称}_{task_id}
        
        Returns:
            迁移统计 {"renamed": N}
        """
        uuid_prefix_pattern = re.compile(
            r'^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})_(.+)$',
            re.IGNORECASE
        )
        stats = {"renamed": 0}
        
        changed = False
        for item in self._history:
            # 检查 lecture_title 是否包含 UUID 前缀或后缀，清理掉
            if item.lecture_title:
                cleaned = re.sub(
                    r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_',
                    '', item.lecture_title, flags=re.IGNORECASE
                )
                cleaned = re.sub(
                    r'_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
                    '', cleaned, flags=re.IGNORECASE
                )
                if cleaned != item.lecture_title:
                    item.lecture_title = cleaned
                    changed = True
            
            # 检查 video_path 的文件名是否是旧命名
            video_path = Path(item.video_path)
            video_stem = video_path.stem
            match = uuid_prefix_pattern.match(video_stem)
            if not match:
                continue  # 已经是新命名或不匹配
            
            task_id = match.group(1)
            original_name = match.group(2)
            
            try:
                # 重命名视频文件: {uuid}_{name}.ext -> {name}_{uuid}.ext
                if video_path.exists():
                    new_video_name = f"{original_name}_{task_id}{video_path.suffix}"
                    new_video_path = video_path.parent / new_video_name
                    video_path.rename(new_video_path)
                    logger.info(f"重命名视频: {video_path.name} -> {new_video_name}")
                else:
                    new_video_path = video_path.parent / f"{original_name}_{task_id}{video_path.suffix}"
                
                # 更新 video_path 和 video_name
                item.video_path = str(Path(item.video_path).parent / new_video_path.name)
                item.video_name = new_video_path.name
                
                # 重命名 output 目录: {uuid}_{name} -> {name}_{uuid}
                output_dir = Path(item.output_dir)
                old_dir_name = output_dir.name
                dir_match = uuid_prefix_pattern.match(old_dir_name)
                if dir_match:
                    new_dir_name = f"{dir_match.group(2)}_{dir_match.group(1)}"
                    new_output_dir = output_dir.parent / new_dir_name
                    
                    if output_dir.exists():
                        # 重命名目录内文件（以旧 base_name 开头的文件）
                        old_base = video_stem  # {uuid}_{name}
                        new_base = f"{original_name}_{task_id}"
                        self._rename_dir_contents(output_dir, old_base, new_base)
                        
                        # 重命名目录本身
                        output_dir.rename(new_output_dir)
                        logger.info(f"重命名输出目录: {old_dir_name} -> {new_dir_name}")
                    
                    # 更新路径
                    old_output_str = item.output_dir
                    new_output_str = str(Path(item.output_dir).parent / new_dir_name)
                    item.output_dir = new_output_str
                    
                    # 更新 srt_path 和 lecture_path
                    for attr in ('srt_path', 'lecture_path'):
                        old_val = getattr(item, attr)
                        if old_val.startswith(old_output_str):
                            new_val = old_val.replace(old_output_str, new_output_str, 1)
                            # 替换文件名中的前缀
                            new_val = new_val.replace(f"/{old_base}.", f"/{new_base}.", 1)
                            setattr(item, attr, new_val)
                
                stats["renamed"] += 1
                changed = True
            except Exception as e:
                logger.error(f"重命名失败 (task {task_id}): {e}")
                continue
        
        if changed:
            self._save()
        
        return stats
    
    @staticmethod
    def _rename_dir_contents(directory: Path, old_prefix: str, new_prefix: str) -> None:
        """重命名目录内以 old_prefix 开头的文件"""
        for entry in directory.iterdir():
            if entry.is_dir():
                # 递归处理子目录（如 segments/）
                HistoryService._rename_dir_contents(entry, old_prefix, new_prefix)
            elif entry.name.startswith(old_prefix):
                new_name = new_prefix + entry.name[len(old_prefix):]
                entry.rename(entry.parent / new_name)
    
    def cleanup_orphan_files(self) -> Dict[str, int]:
        """
        清理不在历史记录中的孤儿文件
        
        Returns:
            清理统计 {"cleaned_uploads": N, "cleaned_outputs": N, "freed_bytes": N}
        """
        config = get_config()
        stats = {"cleaned_uploads": 0, "cleaned_outputs": 0, "freed_bytes": 0}
        
        # 安全检查：历史记录为空时跳过清理
        if not self._history:
            logger.warning("历史记录为空，跳过孤儿文件清理")
            return stats
        
        # 构建有效 task_id 集合
        tracked_ids = {item.id for item in self._history}
        
        # 扫描 uploads/ 目录
        upload_dir = Path(config.storage.upload_dir)
        if upload_dir.exists():
            for entry in upload_dir.iterdir():
                task_id = self._extract_task_id(entry.name)
                if task_id and task_id not in tracked_ids:
                    size = self._get_size(entry)
                    try:
                        if entry.is_dir():
                            shutil.rmtree(entry)
                        else:
                            entry.unlink()
                        stats["cleaned_uploads"] += 1
                        stats["freed_bytes"] += size
                        logger.info(f"清理孤儿文件(uploads): {entry.name}")
                    except Exception as e:
                        logger.error(f"清理失败: {entry} -> {e}")
        
        # 扫描 outputs/ 目录
        output_dir = Path(config.storage.output_dir)
        if output_dir.exists():
            for entry in output_dir.iterdir():
                if entry.name == "history.json":
                    continue
                task_id = self._extract_task_id(entry.name)
                if task_id and task_id not in tracked_ids:
                    size = self._get_size(entry)
                    try:
                        if entry.is_dir():
                            shutil.rmtree(entry)
                        else:
                            entry.unlink()
                        stats["cleaned_outputs"] += 1
                        stats["freed_bytes"] += size
                        logger.info(f"清理孤儿文件(outputs): {entry.name}")
                    except Exception as e:
                        logger.error(f"清理失败: {entry} -> {e}")
        
        return stats
    
    @staticmethod
    def _extract_task_id(name: str) -> Optional[str]:
        """从文件/目录名中提取 task_id（末尾 UUID），验证是否为有效 UUID"""
        stem = Path(name).stem  # 去掉扩展名
        parts = stem.rsplit('_', 1)
        if len(parts) < 2:
            return None
        try:
            uuid_mod.UUID(parts[-1])
            return parts[-1]
        except ValueError:
            # 兼容旧命名 {uuid}_{name}
            parts = stem.split('_', 1)
            if len(parts) < 2:
                return None
            try:
                uuid_mod.UUID(parts[0])
                return parts[0]
            except ValueError:
                return None
    
    @staticmethod
    def _get_size(path: Path) -> int:
        """获取文件或目录的大小"""
        if path.is_file():
            return path.stat().st_size
        total = 0
        try:
            for f in path.rglob('*'):
                if f.is_file():
                    total += f.stat().st_size
        except Exception:
            pass
        return total


# 全局实例
_history_service: Optional[HistoryService] = None


def get_history_service() -> HistoryService:
    """获取历史记录服务实例"""
    global _history_service
    if _history_service is None:
        _history_service = HistoryService()
    return _history_service
