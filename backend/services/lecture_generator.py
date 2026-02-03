"""讲义生成服务 - 使用LLM将口语化内容转换为规范讲义"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from config import get_config
from models.schemas import Section, Lecture, LectureMetadata

logger = logging.getLogger(__name__)

# 讲义生成的系统提示词
LECTURE_GEN_PROMPT = """你是一个专业的教育内容编辑。你的任务是将课程的口语化讲解内容转换为规范、简洁的书面讲义。

请遵循以下规则：
1. 去除口语化表达（如"呃"、"那个"、"就是说"等）
2. 保留核心知识点和概念
3. 使用清晰、专业的书面语言
4. 适当添加Markdown格式（标题、列表、强调等）
5. 保持内容的准确性，不要添加原文没有的信息

输出格式为Markdown，结构清晰，便于阅读。
"""


class LectureGenerator:
    """讲义生成服务"""
    
    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化讲义生成服务
        
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
        logger.info(f"LectureGenerator初始化: model={self.model}")
    
    def _get_client(self) -> OpenAI:
        """获取OpenAI客户端"""
        if self._client is None:
            self._client = OpenAI(
                base_url=self.api_base,
                api_key=self.api_key
            )
        return self._client
    
    def generate_section_content(
        self,
        section_title: str,
        raw_content: str,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        为单个小节生成规范讲义内容
        
        Args:
            section_title: 小节标题
            raw_content: 原始口语化内容
            progress_callback: 进度回调函数
            
        Returns:
            Markdown格式的规范讲义内容
        """
        logger.info(f"生成小节讲义: {section_title}")
        
        if progress_callback:
            progress_callback(10)
        
        # 检查API配置
        if not self.api_key or self.api_key == "your-api-key-here":
            logger.warning("LLM API密钥未配置，使用简单处理")
            return self._simple_process(section_title, raw_content)
        
        try:
            client = self._get_client()
            
            if progress_callback:
                progress_callback(30)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": LECTURE_GEN_PROMPT},
                    {"role": "user", "content": f"小节标题：{section_title}\n\n原始内容：\n{raw_content}\n\n请将上述内容转换为规范的Markdown讲义。"}
                ],
                temperature=1  # kimi-k2.5模型只支持temperature=1
            )
            
            if progress_callback:
                progress_callback(100)
            
            content = response.choices[0].message.content
            logger.info(f"小节讲义生成完成: {section_title}")
            return content
            
        except Exception as e:
            logger.error(f"讲义生成失败: {e}")
            return self._simple_process(section_title, raw_content)
    
    def _simple_process(self, section_title: str, raw_content: str) -> str:
        """简单处理（用于API不可用时）"""
        # 基本的去口语化处理
        filler_words = [
            "呃", "额", "嗯", "那个", "就是说", "然后呢", 
            "对吧", "是吧", "你看", "我们知道"
        ]
        
        content = raw_content
        for word in filler_words:
            content = content.replace(word, "")
        
        # 整理成Markdown格式
        return f"## {section_title}\n\n{content.strip()}"
    
    def generate_lecture(
        self,
        sections: List[Section],
        video_file: str,
        duration: float,
        title: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Lecture:
        """
        生成完整的讲义
        
        Args:
            sections: 小节列表
            video_file: 视频文件名
            duration: 视频时长
            title: 讲义标题，默认根据视频文件名生成
            progress_callback: 进度回调函数 (progress, message)
            
        Returns:
            完整的讲义对象
        """
        logger.info(f"开始生成完整讲义，共{len(sections)}个小节")
        
        if title is None:
            title = Path(video_file).stem
        
        # 为每个小节生成规范内容
        processed_sections = []
        total = len(sections)
        
        for i, section in enumerate(sections):
            if progress_callback:
                progress = int((i / total) * 100)
                progress_callback(progress, f"正在生成第{i + 1}/{total}节讲义...")
            
            # 生成规范内容
            content = self.generate_section_content(
                section.title,
                section.content
            )
            
            processed_sections.append(Section(
                id=section.id,
                title=section.title,
                start_time=section.start_time,
                end_time=section.end_time,
                content=content,
                summary=section.summary
            ))
        
        if progress_callback:
            progress_callback(100, "讲义生成完成")
        
        # 创建讲义对象
        lecture = Lecture(
            title=title,
            sections=processed_sections,
            metadata=LectureMetadata(
                video_file=video_file,
                duration=duration,
                created_at=datetime.now()
            )
        )
        
        logger.info(f"讲义生成完成: {title}")
        return lecture
    
    def save_lecture(self, lecture: Lecture, output_path: str) -> str:
        """
        保存讲义到JSON文件
        
        Args:
            lecture: 讲义对象
            output_path: 输出文件路径
            
        Returns:
            保存的文件路径
        """
        output_path = Path(output_path)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(lecture.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        
        logger.info(f"讲义已保存: {output_path}")
        return str(output_path)
    
    def load_lecture(self, lecture_path: str) -> Lecture:
        """
        从JSON文件加载讲义
        
        Args:
            lecture_path: 讲义文件路径
            
        Returns:
            讲义对象
        """
        with open(lecture_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return Lecture(**data)


# 全局实例
_lecture_generator: Optional[LectureGenerator] = None


def get_lecture_generator() -> LectureGenerator:
    """获取讲义生成服务实例"""
    global _lecture_generator
    if _lecture_generator is None:
        _lecture_generator = LectureGenerator()
    return _lecture_generator
