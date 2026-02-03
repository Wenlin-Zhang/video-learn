"""文本纠错服务 - 使用LLM纠正语音识别文本中的错误"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from config import get_config

logger = logging.getLogger(__name__)

# 文本纠错的系统提示词
TEXT_CORRECTION_PROMPT = """你是一个专业的语音识别文本校对专家。请根据上下文纠正以下语音识别文本中的错误。

纠错规则：
1. 纠正同音字/近音字错误（如"机器学习"被误识别为"机器学系"）
2. 纠正专业术语识别错误
3. 保持原文的标点符号和分段结构
4. 不要添加或删除内容，只纠正明显的识别错误
5. 如果有提供热词列表，优先参考热词进行纠正
6. 保持文本的自然流畅性

请直接输出纠正后的文本，不要添加任何解释、标记或额外内容。"""

# JSON格式文本纠错的系统提示词
JSON_CORRECTION_PROMPT = """你是一个专业的语音识别文本校对专家。请根据上下文纠正以下JSON格式的语音识别结果中的文本错误。

输入是一个JSON对象，包含多个语音片段，每个片段有segment_id、时间信息和识别文本。

纠错规则：
1. 只修改每个片段中的"text"字段内容
2. 纠正同音字/近音字错误（如"机器学习"被误识别为"机器学系"）
3. 纠正专业术语识别错误
4. 保持原文的标点符号
5. 如果有提供热词列表，优先参考热词进行纠正
6. 不要修改segment_id、start_time、end_time等其他字段
7. 保持JSON结构完整，不要添加或删除字段

请直接输出纠正后的JSON，保持完全相同的结构，不要添加任何解释或额外内容。"""


class TextCorrector:
    """语音识别文本纠错服务"""
    
    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化文本纠错服务
        
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
        logger.info(f"TextCorrector初始化: model={self.model}")
    
    def _get_client(self) -> OpenAI:
        """获取OpenAI客户端"""
        if self._client is None:
            self._client = OpenAI(
                base_url=self.api_base,
                api_key=self.api_key
            )
        return self._client
    
    def correct_text(
        self,
        text: str,
        hotwords: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        根据上下文纠正识别文本中的错误
        
        Args:
            text: 原始识别文本
            hotwords: 热词列表，用于辅助纠正专业术语
            progress_callback: 进度回调函数
            
        Returns:
            纠正后的文本
        """
        if not text:
            return ""
        
        logger.info(f"开始文本纠错，原始文本长度: {len(text)}")
        
        if progress_callback:
            progress_callback(10)
        
        # 检查API配置
        if not self.api_key or self.api_key == "your-api-key-here":
            logger.warning("LLM API密钥未配置，跳过文本纠错")
            if progress_callback:
                progress_callback(100)
            return text
        
        try:
            client = self._get_client()
            
            if progress_callback:
                progress_callback(30)
            
            # 构建用户消息
            user_message = ""
            if hotwords:
                hotwords_str = "、".join(hotwords)
                user_message += f"热词列表：{hotwords_str}\n\n"
            
            user_message += f"原始识别文本：\n{text}"
            
            # 对于长文本，分段处理
            max_chunk_size = 8000  # 每段最大字符数
            if len(text) > max_chunk_size:
                corrected_text = self._correct_long_text(
                    text, hotwords, max_chunk_size, progress_callback
                )
            else:
                # 短文本直接处理
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": TEXT_CORRECTION_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=1  # kimi-k2.5模型只支持temperature=1
                )
                
                corrected_text = response.choices[0].message.content
            
            if progress_callback:
                progress_callback(100)
            
            logger.info(f"文本纠错完成，纠正后文本长度: {len(corrected_text)}")
            
            return corrected_text
            
        except Exception as e:
            logger.error(f"文本纠错失败: {e}")
            # 纠错失败时返回原文
            return text
    
    def _correct_long_text(
        self,
        text: str,
        hotwords: Optional[List[str]],
        max_chunk_size: int,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        分段处理长文本
        
        Args:
            text: 长文本
            hotwords: 热词列表
            max_chunk_size: 每段最大字符数
            progress_callback: 进度回调函数
            
        Returns:
            纠正后的完整文本
        """
        # 按句子分割，避免在句子中间断开
        sentences = self._split_into_sentences(text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk += sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.info(f"长文本分为 {len(chunks)} 段进行纠错")
        
        client = self._get_client()
        corrected_chunks = []
        
        for i, chunk in enumerate(chunks):
            chunk_progress_base = 30 + int(60 * i / len(chunks))
            
            if progress_callback:
                progress_callback(chunk_progress_base)
            
            user_message = ""
            if hotwords:
                hotwords_str = "、".join(hotwords)
                user_message += f"热词列表：{hotwords_str}\n\n"
            user_message += f"原始识别文本：\n{chunk}"
            
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": TEXT_CORRECTION_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=1
                )
                
                corrected_chunks.append(response.choices[0].message.content)
                logger.info(f"第 {i+1}/{len(chunks)} 段纠错完成")
                
            except Exception as e:
                logger.error(f"第 {i+1} 段纠错失败: {e}")
                # 失败时保留原文
                corrected_chunks.append(chunk)
        
        return "".join(corrected_chunks)
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        将文本分割成句子
        
        Args:
            text: 原始文本
            
        Returns:
            句子列表
        """
        # 中文和英文的句子结束标点
        sentence_endings = set('。！？.!?')
        
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            if char in sentence_endings:
                sentences.append(current_sentence)
                current_sentence = ""
        
        if current_sentence:
            sentences.append(current_sentence)
        
        return sentences
    
    def correct_segments_json(
        self,
        segments_data: List[Dict[str, Any]],
        hotwords: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        对带时间信息的JSON格式语音识别结果进行纠错
        
        Args:
            segments_data: 语音片段数据列表，每个元素包含:
                - segment_id: 片段ID
                - start_time: 开始时间
                - end_time: 结束时间
                - text: 识别文本
            hotwords: 热词列表
            progress_callback: 进度回调函数
            
        Returns:
            纠正后的片段数据列表
        """
        if not segments_data:
            return []
        
        logger.info(f"开始JSON格式文本纠错，共 {len(segments_data)} 个片段")
        
        if progress_callback:
            progress_callback(10)
        
        # 检查API配置
        if not self.api_key or self.api_key == "your-api-key-here":
            logger.warning("LLM API密钥未配置，跳过文本纠错")
            if progress_callback:
                progress_callback(100)
            return segments_data
        
        try:
            client = self._get_client()
            
            if progress_callback:
                progress_callback(20)
            
            # 构建JSON对象
            json_obj = {"segments": segments_data}
            json_str = json.dumps(json_obj, ensure_ascii=False, indent=2)
            
            # 构建用户消息
            user_message = ""
            if hotwords:
                hotwords_str = "、".join(hotwords)
                user_message += f"热词列表：{hotwords_str}\n\n"
            
            user_message += f"请纠正以下JSON中各片段的text字段：\n```json\n{json_str}\n```"
            
            # 对于超长JSON，分批处理
            max_json_size = 30000  # JSON最大字符数
            if len(json_str) > max_json_size:
                corrected_segments = self._correct_long_json(
                    segments_data, hotwords, progress_callback
                )
            else:
                # 直接处理
                if progress_callback:
                    progress_callback(40)
                
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": JSON_CORRECTION_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=1
                )
                
                if progress_callback:
                    progress_callback(80)
                
                result_text = response.choices[0].message.content
                
                # 解析返回的JSON
                corrected_segments = self._parse_corrected_json(result_text, segments_data)
            
            if progress_callback:
                progress_callback(100)
            
            logger.info(f"JSON格式文本纠错完成")
            return corrected_segments
            
        except Exception as e:
            logger.error(f"JSON格式文本纠错失败: {e}")
            import traceback
            traceback.print_exc()
            # 纠错失败时返回原数据
            return segments_data
    
    def _correct_long_json(
        self,
        segments_data: List[Dict[str, Any]],
        hotwords: Optional[List[str]],
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        分批处理超长JSON
        """
        batch_size = 20  # 每批处理的片段数
        batches = []
        
        for i in range(0, len(segments_data), batch_size):
            batches.append(segments_data[i:i + batch_size])
        
        logger.info(f"超长JSON分为 {len(batches)} 批处理")
        
        client = self._get_client()
        all_corrected = []
        
        for i, batch in enumerate(batches):
            batch_progress = 20 + int(70 * (i + 1) / len(batches))
            if progress_callback:
                progress_callback(batch_progress)
            
            json_obj = {"segments": batch}
            json_str = json.dumps(json_obj, ensure_ascii=False, indent=2)
            
            user_message = ""
            if hotwords:
                hotwords_str = "、".join(hotwords)
                user_message += f"热词列表：{hotwords_str}\n\n"
            user_message += f"请纠正以下JSON中各片段的text字段：\n```json\n{json_str}\n```"
            
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": JSON_CORRECTION_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=1
                )
                
                result_text = response.choices[0].message.content
                corrected_batch = self._parse_corrected_json(result_text, batch)
                all_corrected.extend(corrected_batch)
                
                logger.info(f"第 {i+1}/{len(batches)} 批纠错完成")
                
            except Exception as e:
                logger.error(f"第 {i+1} 批纠错失败: {e}")
                all_corrected.extend(batch)
        
        return all_corrected
    
    def _parse_corrected_json(
        self,
        result_text: str,
        original_segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        解析LLM返回的纠正后JSON
        
        Args:
            result_text: LLM返回的文本
            original_segments: 原始片段数据（用于回退）
            
        Returns:
            解析后的片段数据列表
        """
        try:
            # 尝试直接解析
            result_text = result_text.strip()
            
            # 移除可能的markdown代码块标记
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                # 移除首尾的```行
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                result_text = "\n".join(lines)
            
            parsed = json.loads(result_text)
            
            if "segments" in parsed:
                corrected_segments = parsed["segments"]
            elif isinstance(parsed, list):
                corrected_segments = parsed
            else:
                logger.warning("JSON格式不符合预期，使用原始数据")
                return original_segments
            
            # 验证并合并结果
            result = []
            original_map = {s["segment_id"]: s for s in original_segments}
            
            for corrected in corrected_segments:
                seg_id = corrected.get("segment_id")
                if seg_id in original_map:
                    # 保留原始时间信息，只更新text
                    merged = original_map[seg_id].copy()
                    merged["text"] = corrected.get("text", merged["text"])
                    result.append(merged)
                else:
                    result.append(corrected)
            
            # 补充未被纠正的片段
            corrected_ids = {s.get("segment_id") for s in corrected_segments}
            for seg in original_segments:
                if seg["segment_id"] not in corrected_ids:
                    result.append(seg)
            
            # 按segment_id排序
            result.sort(key=lambda x: x.get("segment_id", 0))
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"原始返回: {result_text[:500]}...")
            return original_segments


# 全局实例
_text_corrector: Optional[TextCorrector] = None


def get_text_corrector() -> TextCorrector:
    """获取文本纠错服务实例"""
    global _text_corrector
    if _text_corrector is None:
        _text_corrector = TextCorrector()
    return _text_corrector
