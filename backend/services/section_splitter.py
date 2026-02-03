"""小节划分服务 - 使用LLM将课程内容划分为小节"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Callable

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from config import get_config
from models.schemas import Section, SubtitleEntry

logger = logging.getLogger(__name__)

# 小节划分的系统提示词
SECTION_SPLIT_PROMPT = """你是一个专业的教育内容分析师。你的任务是将课程讲解内容划分为逻辑清晰的小节。

请根据以下规则进行划分：
1. 每个小节应该是一个相对独立的知识点或主题
2. 小节的划分应该基于内容的逻辑转换点
3. 每个小节需要有一个简洁明确的标题
4. 为每个小节提供开始和结束的字幕索引

请以JSON格式输出，格式如下：
```json
{
  "sections": [
    {
      "title": "小节标题",
      "start_index": 1,
      "end_index": 5,
      "summary": "该小节的内容摘要"
    }
  ]
}
```

注意：
- start_index和end_index是字幕条目的索引（从1开始）
- 确保所有字幕都被分配到某个小节
- 小节之间不要有重叠或遗漏
"""


class SectionSplitter:
    """小节划分服务"""
    
    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化小节划分服务
        
        Args:
            api_base: API基础URL，默认从配置读取
            api_key: API密钥，默认从配置读取
            model: 模型名称，默认从配置读取
        """
        config = get_config()
        self.api_base = api_base or config.llm.api_base
        self.api_key = api_key or config.llm.api_key
        self.model = model or config.llm.model
        
        self._client = None
        logger.info(f"SectionSplitter初始化: model={self.model}")
    
    def _get_client(self) -> OpenAI:
        """获取OpenAI客户端"""
        if self._client is None:
            self._client = OpenAI(
                base_url=self.api_base,
                api_key=self.api_key
            )
        return self._client
    
    def split_sections(
        self,
        subtitles: List[SubtitleEntry],
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> List[dict]:
        """
        将字幕内容划分为小节
        
        Args:
            subtitles: 字幕条目列表
            progress_callback: 进度回调函数
            
        Returns:
            小节信息列表（包含字幕索引范围）
        """
        if not subtitles:
            return []
        
        logger.info(f"开始小节划分，字幕数量: {len(subtitles)}")
        
        if progress_callback:
            progress_callback(10)
        
        # 准备字幕文本
        subtitle_text = self._format_subtitles(subtitles)
        
        # 检查API配置
        if not self.api_key or self.api_key == "your-api-key-here":
            logger.warning("LLM API密钥未配置，使用模拟划分")
            return self._mock_split(subtitles)
        
        try:
            client = self._get_client()
            
            if progress_callback:
                progress_callback(30)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SECTION_SPLIT_PROMPT},
                    {"role": "user", "content": f"请划分以下课程内容的小节：\n\n{subtitle_text}"}
                ],
                temperature=1,  # kimi-k2.5模型只支持temperature=1
                response_format={"type": "json_object"}
            )
            
            if progress_callback:
                progress_callback(80)
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            sections = result.get("sections", [])
            
            if progress_callback:
                progress_callback(100)
            
            logger.info(f"小节划分完成，小节数量: {len(sections)}")
            return sections
            
        except Exception as e:
            logger.error(f"小节划分失败: {e}")
            # 降级到模拟划分
            return self._mock_split(subtitles)
    
    def _format_subtitles(self, subtitles: List[SubtitleEntry]) -> str:
        """格式化字幕用于LLM输入"""
        lines = []
        for sub in subtitles:
            lines.append(f"[{sub.index}] {sub.text}")
        return "\n".join(lines)
    
    def _mock_split(self, subtitles: List[SubtitleEntry]) -> List[dict]:
        """模拟小节划分（用于开发测试或API不可用时）"""
        if not subtitles:
            return []
        
        # 简单策略：每5-10条字幕划分为一个小节
        sections = []
        section_size = min(8, max(3, len(subtitles) // 3))
        
        start_idx = 1
        section_num = 1
        
        while start_idx <= len(subtitles):
            end_idx = min(start_idx + section_size - 1, len(subtitles))
            
            # 获取小节内容
            section_subs = [s for s in subtitles if start_idx <= s.index <= end_idx]
            section_text = " ".join(s.text for s in section_subs)
            
            sections.append({
                "title": f"第{section_num}节",
                "start_index": start_idx,
                "end_index": end_idx,
                "summary": section_text[:50] + "..." if len(section_text) > 50 else section_text
            })
            
            start_idx = end_idx + 1
            section_num += 1
        
        return sections
    
    def create_sections_with_time(
        self,
        section_info: List[dict],
        subtitles: List[SubtitleEntry]
    ) -> List[Section]:
        """
        根据划分信息和字幕时间创建带时间戳的小节
        
        Args:
            section_info: 小节划分信息
            subtitles: 字幕条目列表
            
        Returns:
            带时间戳的小节列表
        """
        # 创建索引映射
        sub_map = {s.index: s for s in subtitles}
        
        sections = []
        for i, info in enumerate(section_info):
            start_idx = info["start_index"]
            end_idx = info["end_index"]
            
            # 获取时间范围
            start_sub = sub_map.get(start_idx)
            end_sub = sub_map.get(end_idx)
            
            if start_sub and end_sub:
                # 收集小节内的所有字幕文本
                section_text = " ".join(
                    sub_map[idx].text 
                    for idx in range(start_idx, end_idx + 1) 
                    if idx in sub_map
                )
                
                sections.append(Section(
                    id=i + 1,
                    title=info.get("title", f"第{i + 1}节"),
                    start_time=start_sub.start_time,
                    end_time=end_sub.end_time,
                    content=section_text,  # 稍后会被讲义生成服务替换
                    summary=info.get("summary", "")
                ))
        
        return sections


# 全局实例
_section_splitter: Optional[SectionSplitter] = None


def get_section_splitter() -> SectionSplitter:
    """获取小节划分服务实例"""
    global _section_splitter
    if _section_splitter is None:
        _section_splitter = SectionSplitter()
    return _section_splitter
