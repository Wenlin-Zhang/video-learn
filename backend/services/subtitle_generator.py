"""字幕生成服务 - 生成SRT格式字幕文件"""
import logging
from pathlib import Path
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import SubtitleEntry, WordTimestamp

logger = logging.getLogger(__name__)


def format_time_srt(seconds: float) -> str:
    """
    将秒数转换为SRT时间格式 (HH:MM:SS,mmm)
    
    Args:
        seconds: 时间（秒）
        
    Returns:
        SRT格式时间字符串
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class SubtitleGenerator:
    """字幕生成器"""
    
    def __init__(
        self,
        max_chars_per_line: int = 40,
        max_duration: float = 5.0,
        min_duration: float = 1.0
    ):
        """
        初始化字幕生成器
        
        Args:
            max_chars_per_line: 每行最大字符数
            max_duration: 单条字幕最大时长（秒）
            min_duration: 单条字幕最小时长（秒）
        """
        self.max_chars_per_line = max_chars_per_line
        self.max_duration = max_duration
        self.min_duration = min_duration
    
    def generate_entries(
        self,
        words: List[WordTimestamp]
    ) -> List[SubtitleEntry]:
        """
        根据词级时间戳生成字幕条目
        
        Args:
            words: 词级时间戳列表
            
        Returns:
            字幕条目列表
        """
        if not words:
            return []
        
        entries = []
        current_text = ""
        current_start = words[0].start_time
        current_end = words[0].end_time
        entry_index = 1
        
        # 句子结束符号
        sentence_end_marks = set('。！？.!?')
        # 分句符号
        clause_marks = set('，；,;')
        
        for i, word in enumerate(words):
            # 添加当前词
            current_text += word.word
            current_end = word.end_time
            
            # 判断是否需要切分
            should_split = False
            
            # 条件1: 遇到句子结束符
            if word.word in sentence_end_marks:
                should_split = True
            
            # 条件2: 超过最大字符数
            elif len(current_text) >= self.max_chars_per_line:
                should_split = True
            
            # 条件3: 超过最大时长
            elif current_end - current_start >= self.max_duration:
                should_split = True
            
            # 条件4: 遇到分句符号且已有一定长度
            elif word.word in clause_marks and len(current_text) >= 15:
                should_split = True
            
            if should_split and current_text.strip():
                entries.append(SubtitleEntry(
                    index=entry_index,
                    start_time=current_start,
                    end_time=current_end,
                    text=current_text.strip()
                ))
                entry_index += 1
                current_text = ""
                if i + 1 < len(words):
                    current_start = words[i + 1].start_time
        
        # 处理剩余文本
        if current_text.strip():
            entries.append(SubtitleEntry(
                index=entry_index,
                start_time=current_start,
                end_time=current_end,
                text=current_text.strip()
            ))
        
        return entries
    
    def to_srt(self, entries: List[SubtitleEntry]) -> str:
        """
        将字幕条目转换为SRT格式字符串
        
        Args:
            entries: 字幕条目列表
            
        Returns:
            SRT格式字符串
        """
        lines = []
        for entry in entries:
            lines.append(str(entry.index))
            lines.append(
                f"{format_time_srt(entry.start_time)} --> {format_time_srt(entry.end_time)}"
            )
            lines.append(entry.text)
            lines.append("")  # 空行分隔
        
        return "\n".join(lines)
    
    def save_srt(
        self,
        entries: List[SubtitleEntry],
        output_path: str
    ) -> str:
        """
        保存字幕文件
        
        Args:
            entries: 字幕条目列表
            output_path: 输出文件路径
            
        Returns:
            保存的文件路径
        """
        output_path = Path(output_path)
        srt_content = self.to_srt(entries)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        
        logger.info(f"字幕文件已保存: {output_path}")
        return str(output_path)


def generate_srt(
    words: List[WordTimestamp],
    output_path: str,
    max_chars_per_line: int = 40
) -> str:
    """
    便捷函数：生成SRT字幕文件
    
    Args:
        words: 词级时间戳列表
        output_path: 输出文件路径
        max_chars_per_line: 每行最大字符数
        
    Returns:
        保存的文件路径
    """
    generator = SubtitleGenerator(max_chars_per_line=max_chars_per_line)
    entries = generator.generate_entries(words)
    return generator.save_srt(entries, output_path)


def parse_srt(srt_path: str) -> List[SubtitleEntry]:
    """
    解析SRT字幕文件
    
    Args:
        srt_path: SRT文件路径
        
    Returns:
        字幕条目列表
    """
    import re
    
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    entries = []
    blocks = content.strip().split("\n\n")
    
    time_pattern = re.compile(
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
    )
    
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) >= 3:
            try:
                index = int(lines[0])
                time_match = time_pattern.match(lines[1])
                if time_match:
                    g = time_match.groups()
                    start_time = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
                    end_time = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
                    text = "\n".join(lines[2:])
                    
                    entries.append(SubtitleEntry(
                        index=index,
                        start_time=start_time,
                        end_time=end_time,
                        text=text
                    ))
            except (ValueError, IndexError):
                continue
    
    return entries
