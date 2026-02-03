"""中间结果管理服务"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """阶段状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# 阶段定义（顺序很重要）
STAGE_DEFINITIONS = [
    {"id": 1, "name": "extract_audio", "label": "提取音频"},
    {"id": 2, "name": "asr", "label": "语音识别"},
    {"id": 3, "name": "text_correct", "label": "文本纠错"},
    {"id": 4, "name": "align", "label": "时间对齐"},
    {"id": 5, "name": "subtitle", "label": "生成字幕"},
    {"id": 6, "name": "section_split", "label": "划分小节"},
    {"id": 7, "name": "lecture_gen", "label": "生成讲义"},
]


def get_stage_id(stage_name: str) -> Optional[int]:
    """根据阶段名称获取阶段ID"""
    for stage in STAGE_DEFINITIONS:
        if stage["name"] == stage_name:
            return stage["id"]
    return None


def get_stage_name(stage_id: int) -> Optional[str]:
    """根据阶段ID获取阶段名称"""
    for stage in STAGE_DEFINITIONS:
        if stage["id"] == stage_id:
            return stage["name"]
    return None


class IntermediateService:
    """中间结果管理服务"""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.intermediate_dir = self.output_dir / "intermediate"
        self.intermediate_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.intermediate_dir / "pipeline_state.json"
    
    def initialize_pipeline(
        self, 
        task_id: str, 
        video_name: str, 
        video_path: str,
        hotwords: Optional[List[str]] = None,
        duration: Optional[float] = None
    ) -> Dict[str, Any]:
        """初始化处理流程状态"""
        now = datetime.now().isoformat()
        state = {
            "task_id": task_id,
            "video_name": video_name,
            "video_path": video_path,
            "output_dir": str(self.output_dir),
            "created_at": now,
            "updated_at": now,
            "duration": duration,
            "stages": [
                {
                    "stage_id": stage["id"],
                    "stage_name": stage["name"],
                    "stage_label": stage["label"],
                    "status": StageStatus.PENDING.value,
                    "started_at": None,
                    "completed_at": None,
                    "result_file": None,
                    "error": None
                }
                for stage in STAGE_DEFINITIONS
            ],
            "hotwords": hotwords or [],
            "metadata": {
                "version": "1.0"
            }
        }
        self._save_state(state)
        logger.info(f"初始化流程状态: {task_id}")
        return state
    
    def load_pipeline_state(self) -> Optional[Dict[str, Any]]:
        """加载处理流程状态"""
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载流程状态失败: {e}")
            return None
    
    def _save_state(self, state: Dict[str, Any]):
        """保存流程状态"""
        state["updated_at"] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    
    def update_stage_status(
        self, 
        stage_name: str, 
        status: StageStatus,
        error: Optional[str] = None
    ):
        """更新阶段状态"""
        state = self.load_pipeline_state()
        if not state:
            logger.warning(f"流程状态不存在，无法更新阶段 {stage_name}")
            return
        
        now = datetime.now().isoformat()
        for stage in state["stages"]:
            if stage["stage_name"] == stage_name:
                stage["status"] = status.value
                if status == StageStatus.IN_PROGRESS:
                    stage["started_at"] = now
                    stage["error"] = None
                elif status in [StageStatus.COMPLETED, StageStatus.FAILED]:
                    stage["completed_at"] = now
                if error:
                    stage["error"] = error
                if status == StageStatus.COMPLETED:
                    stage["result_file"] = f"stage_{stage['stage_id']}_{stage_name}.json"
                break
        
        self._save_state(state)
        logger.info(f"更新阶段状态: {stage_name} -> {status.value}")
    
    def update_duration(self, duration: float):
        """更新视频时长"""
        state = self.load_pipeline_state()
        if state:
            state["duration"] = duration
            self._save_state(state)
    
    def save_stage_result(self, stage_name: str, data: Dict[str, Any]):
        """保存阶段结果"""
        stage_id = get_stage_id(stage_name)
        if stage_id is None:
            raise ValueError(f"未知阶段: {stage_name}")
        
        result = {
            "stage_name": stage_name,
            "completed_at": datetime.now().isoformat(),
            "data": data
        }
        
        result_file = self.intermediate_dir / f"stage_{stage_id}_{stage_name}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"保存阶段结果: {stage_name} -> {result_file}")
    
    def load_stage_result(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """加载阶段结果"""
        stage_id = get_stage_id(stage_name)
        if stage_id is None:
            return None
        
        result_file = self.intermediate_dir / f"stage_{stage_id}_{stage_name}.json"
        if not result_file.exists():
            logger.warning(f"阶段结果文件不存在: {result_file}")
            return None
        
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                return result_data.get("data")
        except Exception as e:
            logger.error(f"加载阶段结果失败: {stage_name}, {e}")
            return None
    
    def get_completed_stages(self) -> List[str]:
        """获取所有已完成的阶段名称"""
        state = self.load_pipeline_state()
        if not state:
            return []
        return [
            stage["stage_name"] 
            for stage in state["stages"] 
            if stage["status"] == StageStatus.COMPLETED.value
        ]
    
    def can_start_from_stage(self, stage_name: str) -> bool:
        """检查是否可以从指定阶段开始处理"""
        state = self.load_pipeline_state()
        if not state:
            return False
        
        target_stage_id = get_stage_id(stage_name)
        if target_stage_id is None:
            return False
        
        # 如果是第一个阶段，总是可以开始
        if target_stage_id == 1:
            return True
        
        # 检查前置阶段是否都已完成
        for stage in state["stages"]:
            if stage["stage_id"] < target_stage_id:
                if stage["status"] != StageStatus.COMPLETED.value:
                    return False
        
        return True
    
    def mark_stages_for_reprocess(self, start_stage_name: str):
        """标记从指定阶段开始需要重新处理的阶段"""
        state = self.load_pipeline_state()
        if not state:
            return
        
        start_stage_id = get_stage_id(start_stage_name)
        if start_stage_id is None:
            return
        
        # 将起始阶段及后续阶段标记为pending
        for stage in state["stages"]:
            if stage["stage_id"] >= start_stage_id:
                stage["status"] = StageStatus.PENDING.value
                stage["started_at"] = None
                stage["completed_at"] = None
                stage["error"] = None
                stage["result_file"] = None  # 清除结果文件引用
        
        self._save_state(state)
        logger.info(f"标记从 {start_stage_name} 开始重新处理")
    
    def get_stage_info(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """获取指定阶段的信息"""
        state = self.load_pipeline_state()
        if not state:
            return None
        
        for stage in state["stages"]:
            if stage["stage_name"] == stage_name:
                return stage
        return None
