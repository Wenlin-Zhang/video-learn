"""语音识别服务 - 使用Qwen3-ASR进行语音转文字和时间对齐

支持两种后端：
- vLLM后端：更快的推理速度，支持大批量处理
- Transformers后端：兼容性更好

功能特性：
- 统一API同时进行语音识别和时间对齐
- 支持FlashAttention加速
- 可配置的max_inference_batch_size防止OOM
- 自动恢复标点符号到对齐结果
- VAD切分长音频防止显存溢出
- 支持从文件名动态提取热词
"""
import logging
import re
from pathlib import Path
from typing import List, Optional, Callable

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from models.schemas import WordTimestamp, TranscriptionResult

logger = logging.getLogger(__name__)


def extract_keywords_from_filename(filename: str) -> List[str]:
    """
    从文件名中提取关键词作为热词
    
    支持的分隔符：下划线、连字符、空格、中文括号、英文括号等
    过滤掉：数字序号、日期、常见无意义词汇、短字母组合
    
    Args:
        filename: 文件名（不含扩展名）
        
    Returns:
        提取的关键词列表
    """
    # 移除扩展名
    name = Path(filename).stem
    
    # 移除任务ID前缀（UUID格式: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx_）
    uuid_pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_'
    name = re.sub(uuid_pattern, '', name, flags=re.IGNORECASE)
    
    # 使用多种分隔符分割
    # 中文括号、英文括号、下划线、连字符、空格、点号
    parts = re.split(r'[_\-\s\.\(\)\[\]【】（）《》]', name)
    
    keywords = []
    # 过滤无意义词汇
    skip_patterns = [
        r'^\d+$',           # 纯数字
        r'^[a-f0-9]{6,}$',  # 十六进制串（可能是ID）
        r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$',  # 日期格式
        r'^第?\d+[章节课讲集期]?$',  # 章节编号
        r'^[a-zA-Z]{1,5}\d*$',  # 短字母+可选数字（如v1, abc123）
        r'^(mp4|avi|mkv|mov|wmv|flv|webm)$',  # 视频扩展名
        r'^(视频|录像|录制|课程|教程|讲座)$',  # 通用词汇
    ]
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # 检查是否匹配过滤模式
        should_skip = False
        for pattern in skip_patterns:
            if re.match(pattern, part, re.IGNORECASE):
                should_skip = True
                break
        
        # 至少2个字符，且包含中文或足够长的英文
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', part))
        if not should_skip and (has_chinese and len(part) >= 2 or not has_chinese and len(part) >= 4):
            keywords.append(part)
    
    # 去重并保持顺序
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    logger.info(f"从文件名提取关键词: {filename} -> {unique_keywords}")
    return unique_keywords


def restore_punctuation(
    original_text: str,
    words: List[WordTimestamp]
) -> List[WordTimestamp]:
    """
    将原始带标点文本中的标点符号恢复到词列表中
    
    ForcedAligner返回的词列表不包含标点，此函数将原始文本中的标点
    附加到对应词的后面。
    
    Args:
        original_text: ASR返回的带标点原始文本
        words: ForcedAligner返回的词级时间戳列表（不带标点）
        
    Returns:
        恢复标点后的词级时间戳列表
    """
    if not words or not original_text:
        return words
    
    # 中文和英文标点符号
    punctuation = set('，。！？、；：""''（）【】《》…—,.!?;:\'"()[]<>')
    
    # 从原始文本中提取非标点字符序列和对应的后续标点
    result_words = []
    text_pos = 0
    word_idx = 0
    
    while word_idx < len(words) and text_pos < len(original_text):
        word = words[word_idx]
        word_text = word.word
        
        # 跳过原始文本中的标点和空白
        while text_pos < len(original_text) and (
            original_text[text_pos] in punctuation or 
            original_text[text_pos].isspace()
        ):
            text_pos += 1
        
        # 在原始文本中找到当前词
        found_pos = original_text.find(word_text, text_pos)
        if found_pos == -1:
            # 如果找不到完全匹配，尝试逐字符匹配
            found_pos = text_pos
            for char in word_text:
                char_pos = original_text.find(char, found_pos)
                if char_pos != -1:
                    found_pos = char_pos + 1
        
        if found_pos != -1:
            text_pos = found_pos + len(word_text) if found_pos >= text_pos else text_pos + len(word_text)
        else:
            text_pos += len(word_text)
        
        # 收集词后面的标点符号
        trailing_punct = ""
        while text_pos < len(original_text) and original_text[text_pos] in punctuation:
            trailing_punct += original_text[text_pos]
            text_pos += 1
        
        # 创建带标点的词
        new_word = WordTimestamp(
            word=word_text + trailing_punct,
            start_time=word.start_time,
            end_time=word.end_time
        )
        result_words.append(new_word)
        word_idx += 1
    
    # 处理剩余的词（如果有）
    while word_idx < len(words):
        result_words.append(words[word_idx])
        word_idx += 1
    
    logger.info(f"标点恢复完成: {len(result_words)} 个词")
    if result_words:
        logger.info(f"前3个词(带标点): {[w.word for w in result_words[:3]]}")
    
    return result_words


class ASRService:
    """语音识别服务 - 支持vLLM和Transformers双后端"""
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        aligner_model: Optional[str] = None,
        backend: Optional[str] = None,
        gpu_memory_utilization: Optional[float] = None,
        max_inference_batch_size: Optional[int] = None,
        max_new_tokens: Optional[int] = None,
        use_flash_attention: Optional[bool] = None,
        language: Optional[str] = None,
        hotwords: Optional[List[str]] = None,
    ):
        """
        初始化ASR服务
        
        Args:
            model_name: ASR模型名称
            aligner_model: ForcedAligner模型名称
            backend: 后端类型 "vllm" 或 "transformers"
            gpu_memory_utilization: vLLM GPU显存利用率
            max_inference_batch_size: 推理批处理大小
            max_new_tokens: 最大生成token数
            use_flash_attention: 是否使用FlashAttention
            language: 默认语言
            hotwords: 热词列表，用于上下文注入
        """
        config = get_config()
        self.model_name = model_name or config.asr.model
        self.aligner_model = aligner_model or config.asr.aligner_model
        self.backend = backend or config.asr.backend
        self.gpu_memory_utilization = gpu_memory_utilization or config.asr.gpu_memory_utilization
        self.max_inference_batch_size = max_inference_batch_size or config.asr.max_inference_batch_size
        self.max_new_tokens = max_new_tokens or config.asr.max_new_tokens
        self.use_flash_attention = use_flash_attention if use_flash_attention is not None else config.asr.use_flash_attention
        self.language = language or config.asr.language
        self.hotwords = hotwords if hotwords is not None else config.asr.hotwords
        self._model = None
        
        # 构建热词上下文字符串
        self._context = self._build_hotwords_context()
        
        logger.info(
            f"ASR服务初始化: model={self.model_name}, "
            f"backend={self.backend}, gpu_util={self.gpu_memory_utilization}, "
            f"max_batch={self.max_inference_batch_size}, flash_attn={self.use_flash_attention}, "
            f"hotwords_count={len(self.hotwords)}"
        )
    
    def _build_hotwords_context(self, extra_hotwords: Optional[List[str]] = None) -> str:
        """
        构建热词上下文字符串
        
        将配置中的热词和动态热词合并，转换为适合上下文注入的格式。
        
        Args:
            extra_hotwords: 额外的动态热词列表（如从文件名提取的关键词）
        
        Returns:
            热词上下文字符串
        """
        # 合并配置热词和动态热词
        all_hotwords = list(self.hotwords) if self.hotwords else []
        if extra_hotwords:
            # 添加动态热词到前面（优先级更高）
            for hw in extra_hotwords:
                if hw not in all_hotwords:
                    all_hotwords.insert(0, hw)
        
        if not all_hotwords:
            return ""
        
        # 将热词用逗号分隔，形成上下文提示
        context = "、".join(all_hotwords)
        logger.info(f"热词上下文({len(all_hotwords)}个): {context[:100]}{'...' if len(context) > 100 else ''}")
        return context
    
    def _load_model(self):
        """延迟加载模型"""
        if self._model is not None:
            return
            
        logger.info(f"加载ASR模型（{self.backend}后端）: {self.model_name}")
        logger.info(f"加载ForcedAligner模型: {self.aligner_model}")
        
        try:
            import torch
            import gc
            from qwen_asr import Qwen3ASRModel
            
            # 清理GPU缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            # 构建ForcedAligner参数
            aligner_kwargs = {
                "dtype": torch.bfloat16,
                "device_map": "cuda:0",
            }
            if self.use_flash_attention:
                aligner_kwargs["attn_implementation"] = "flash_attention_2"
            
            if self.backend == "vllm":
                # vLLM后端 - 更快的推理速度
                logger.info("使用vLLM后端初始化模型...")
                self._model = Qwen3ASRModel.LLM(
                    model=self.model_name,
                    gpu_memory_utilization=self.gpu_memory_utilization,
                    max_inference_batch_size=self.max_inference_batch_size,
                    max_new_tokens=self.max_new_tokens,
                    forced_aligner=self.aligner_model,
                    forced_aligner_kwargs=aligner_kwargs,
                )
            else:
                # Transformers后端 - 兼容性更好
                logger.info("使用Transformers后端初始化模型...")
                model_kwargs = {
                    "dtype": torch.bfloat16,
                    "device_map": "auto",
                    "low_cpu_mem_usage": True,
                    "max_inference_batch_size": self.max_inference_batch_size,
                    "max_new_tokens": self.max_new_tokens,
                    "forced_aligner": self.aligner_model,
                    "forced_aligner_kwargs": aligner_kwargs,
                }
                if self.use_flash_attention:
                    model_kwargs["attn_implementation"] = "flash_attention_2"
                    
                self._model = Qwen3ASRModel.from_pretrained(
                    self.model_name,
                    **model_kwargs
                )
            
            logger.info(f"模型加载完成，后端: {self._model.backend}")
            logger.info(f"ForcedAligner已加载: {self._model.forced_aligner is not None}")
            
        except ImportError as e:
            if "vllm" in str(e).lower():
                logger.warning("vLLM未安装，回退到Transformers后端")
                self.backend = "transformers"
                self._model = None
                self._load_model()
            else:
                logger.warning("qwen_asr库未安装，使用模拟模式")
                self._model = "mock"
        except Exception as e:
            logger.error(f"ASR模型加载失败: {e}")
            raise
    
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        return_timestamps: bool = True,
        extra_hotwords: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> TranscriptionResult:
        """
        对音频进行语音识别（可同时获取时间戳）
        
        Args:
            audio_path: 音频文件路径
            language: 语言
            return_timestamps: 是否返回词级时间戳
            extra_hotwords: 额外的动态热词列表（如从文件名提取的关键词）
            progress_callback: 进度回调函数
            
        Returns:
            TranscriptionResult: 识别结果
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        lang = language or self.language
        logger.info(f"开始语音识别: {audio_path}, 后端: {self.backend}, 时间戳: {return_timestamps}")
        
        self._load_model()
        
        if progress_callback:
            progress_callback(10)
        
        if self._model == "mock":
            logger.warning("使用模拟ASR结果")
            return self._mock_transcribe(audio_path)
        
        try:
            import torch
            import gc
            
            # 清理GPU缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            # 构建热词上下文（合并配置热词和动态热词）
            context = self._build_hotwords_context(extra_hotwords)
            
            # 调用统一API（带热词上下文注入）
            logger.info("调用transcribe()方法...")
            if context:
                logger.info(f"使用热词上下文注入")
            results = self._model.transcribe(
                audio=str(audio_path),
                context=context,  # 热词上下文注入
                language=lang,
                return_time_stamps=return_timestamps,
            )
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            if progress_callback:
                progress_callback(80)
            
            # 解析结果
            logger.info(f"ASR返回结果数量: {len(results)}")
            
            if not results:
                logger.warning("ASR返回空结果")
                return TranscriptionResult(text="", words=[], duration=0.0)
            
            result = results[0]
            text = result.text or ""
            detected_language = result.language or lang
            
            logger.info(f"识别文本长度: {len(text)}, 语言: {detected_language}")
            
            # 解析时间戳
            words = []
            if return_timestamps and result.time_stamps is not None:
                logger.info(f"时间戳类型: {type(result.time_stamps)}")
                for item in result.time_stamps:
                    words.append(WordTimestamp(
                        word=item.text,
                        start_time=float(item.start_time),
                        end_time=float(item.end_time)
                    ))
                logger.info(f"解析到 {len(words)} 个词级时间戳（无标点）")
                if words:
                    logger.info(f"前3个词(无标点): {[(w.word, w.start_time, w.end_time) for w in words[:3]]}")
                
                # 恢复标点符号
                words = restore_punctuation(text, words)
            
            duration = words[-1].end_time if words else 0.0
            
            if progress_callback:
                progress_callback(100)
            
            logger.info(f"语音识别完成，文本长度: {len(text)}, 词数: {len(words)}")
            
            return TranscriptionResult(
                text=text,
                words=words,
                duration=duration
            )
            
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"ASR failed: {e}") from e
    
    def transcribe_text_only(
        self,
        audio_path: str,
        language: Optional[str] = None,
        extra_hotwords: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        仅进行语音识别，返回识别文本（不进行时间对齐）
        
        Args:
            audio_path: 音频文件路径
            language: 语言
            extra_hotwords: 额外的动态热词列表
            progress_callback: 进度回调函数
            
        Returns:
            识别的文本
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        lang = language or self.language
        logger.info(f"开始语音识别(仅文本): {audio_path}, 后端: {self.backend}")
        
        self._load_model()
        
        if progress_callback:
            progress_callback(10)
        
        if self._model == "mock":
            logger.warning("使用模拟ASR结果")
            return self._mock_transcribe(audio_path).text
        
        try:
            import torch
            import gc
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            context = self._build_hotwords_context(extra_hotwords)
            
            logger.info("调用transcribe()方法(仅文本)...")
            results = self._model.transcribe(
                audio=str(audio_path),
                context=context,
                language=lang,
                return_time_stamps=False,  # 不返回时间戳
            )
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            if progress_callback:
                progress_callback(100)
            
            if not results:
                logger.warning("ASR返回空结果")
                return ""
            
            text = results[0].text or ""
            logger.info(f"语音识别完成(仅文本)，文本长度: {len(text)}")
            
            return text
            
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"ASR failed: {e}") from e
    
    def align_text(
        self,
        audio_path: str,
        text: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> List[WordTimestamp]:
        """
        对给定文本进行时间对齐
        
        使用ForcedAligner将文本与音频对齐，获取词级时间戳
        
        Args:
            audio_path: 音频文件路径
            text: 要对齐的文本
            language: 语言，默认使用配置中的语言
            progress_callback: 进度回调函数
            
        Returns:
            词级时间戳列表
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        if not text:
            logger.warning("对齐文本为空")
            return []
        
        lang = language or self.language
        logger.info(f"开始时间对齐: {audio_path}, 文本长度: {len(text)}")
        
        self._load_model()
        
        if progress_callback:
            progress_callback(10)
        
        if self._model == "mock":
            logger.warning("使用模拟对齐结果")
            return self._mock_align(text)
        
        try:
            import torch
            import gc
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            logger.info("调用forced_aligner.align()方法...")
            
            # 直接使用ForcedAligner进行对齐
            aligner = self._model.forced_aligner
            if aligner is None:
                raise RuntimeError("ForcedAligner未加载")
            
            # 必须显式传入language参数
            align_results = aligner.align(
                audio=str(audio_path),
                text=text,
                language=lang,
            )
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            if progress_callback:
                progress_callback(80)
            
            # 解析对齐结果
            # align_results 是列表（包含ForcedAlignResult对象）
            words = []
            
            # 处理返回值：列表中的每个元素是 ForcedAlignResult
            if isinstance(align_results, list):
                for result in align_results:
                    # ForcedAlignResult 实现了 __iter__，可以直接迭代获取 ForcedAlignItem
                    for item in result:
                        words.append(WordTimestamp(
                            word=item.text,
                            start_time=float(item.start_time),
                            end_time=float(item.end_time)
                        ))
            else:
                # 单个 ForcedAlignResult 对象（兼容旧版本）
                for item in align_results:
                    words.append(WordTimestamp(
                        word=item.text,
                        start_time=float(item.start_time),
                        end_time=float(item.end_time)
                    ))
            
            logger.info(f"时间对齐完成，词数: {len(words)}")
            
            # 恢复标点符号
            words = restore_punctuation(text, words)
            
            if progress_callback:
                progress_callback(100)
            
            return words
            
        except Exception as e:
            logger.error(f"时间对齐失败: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Alignment failed: {e}") from e
    
    def _mock_align(self, text: str) -> List[WordTimestamp]:
        """模拟时间对齐"""
        punctuation = set('，。！？、；：""''（）【】《》…—')
        words = []
        current_time = 0.0
        current_word = ""
        word_start = current_time
        
        for char in text:
            if char.isspace():
                continue
            elif char in punctuation:
                if current_word:
                    current_word += char
                    words.append(WordTimestamp(
                        word=current_word,
                        start_time=word_start,
                        end_time=current_time
                    ))
                    current_word = ""
                    current_time += 0.3
            else:
                if current_word:
                    words.append(WordTimestamp(
                        word=current_word,
                        start_time=word_start,
                        end_time=current_time
                    ))
                current_word = char
                word_start = current_time
                current_time += 0.25
        
        if current_word:
            words.append(WordTimestamp(
                word=current_word,
                start_time=word_start,
                end_time=current_time
            ))
        
        return words

    def transcribe_long_audio(
        self,
        audio_path: str,
        output_dir: str,
        language: Optional[str] = None,
        return_timestamps: bool = True,
        max_segment_duration: float = 300.0,
        extra_hotwords: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> TranscriptionResult:
        """
        对长音频进行语音识别（使用VAD切分防止显存溢出）
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录（用于存放临时片段）
            language: 语言
            return_timestamps: 是否返回词级时间戳
            max_segment_duration: 最大片段时长（秒），默认5分钟
            extra_hotwords: 额外的动态热词列表（如从文件名提取的关键词）
            progress_callback: 进度回调函数
            
        Returns:
            TranscriptionResult: 合并后的识别结果
        """
        from services.vad_service import VADService
        
        audio_path = Path(audio_path)
        output_dir = Path(output_dir)
        segments_dir = output_dir / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"开始长音频识别: {audio_path}")
        if extra_hotwords:
            logger.info(f"动态热词: {extra_hotwords}")
        
        # 阶段1: VAD切分 (0-20%)
        if progress_callback:
            progress_callback(0)
        
        vad = VADService(max_segment_duration=max_segment_duration)
        segments = vad.segment_audio(
            str(audio_path),
            str(segments_dir),
            progress_callback=lambda p: progress_callback(int(p * 0.2)) if progress_callback else None
        )
        
        logger.info(f"音频切分完成，共 {len(segments)} 个片段")
        
        if not segments:
            logger.warning("VAD未检测到语音片段")
            return TranscriptionResult(text="", words=[], duration=0.0)
        
        # 阶段2: 逐片段识别 (20-90%)
        all_texts = []
        all_words = []
        
        for i, segment in enumerate(segments):
            segment_progress_base = 20 + int(70 * i / len(segments))
            segment_progress_range = 70 // len(segments)
            
            if progress_callback:
                progress_callback(segment_progress_base)
            
            logger.info(f"识别片段 {i+1}/{len(segments)}: {segment.start_time:.1f}s - {segment.end_time:.1f}s")
            
            # 识别单个片段
            try:
                result = self.transcribe(
                    segment.file_path,
                    language=language,
                    return_timestamps=return_timestamps,
                    extra_hotwords=extra_hotwords,
                    progress_callback=lambda p: progress_callback(
                        segment_progress_base + int(p * segment_progress_range / 100)
                    ) if progress_callback else None
                )
                
                # 调整时间偏移
                offset = segment.start_time
                adjusted_words = []
                for word in result.words:
                    adjusted_words.append(WordTimestamp(
                        word=word.word,
                        start_time=word.start_time + offset,
                        end_time=word.end_time + offset
                    ))
                
                all_texts.append(result.text)
                all_words.extend(adjusted_words)
                
            except Exception as e:
                logger.error(f"片段 {i+1} 识别失败: {e}")
                # 继续处理其他片段
                continue
        
        # 阶段3: 合并结果 (90-100%)
        if progress_callback:
            progress_callback(90)
        
        merged_text = "".join(all_texts)
        duration = all_words[-1].end_time if all_words else 0.0
        
        if progress_callback:
            progress_callback(100)
        
        logger.info(f"长音频识别完成，文本长度: {len(merged_text)}, 词数: {len(all_words)}")
        
        return TranscriptionResult(
            text=merged_text,
            words=all_words,
            duration=duration
        )
    
    def _mock_transcribe(self, audio_path: Path) -> TranscriptionResult:
        """模拟语音识别（带标点）"""
        mock_text = (
            "今天我们来学习机器学习的基本概念。"
            "首先，让我们了解什么是监督学习。"
            "监督学习是一种从标记的训练数据中学习的方法。"
        )
        
        # 中文标点符号
        punctuation = set('，。！？、；：""''（）【】《》…—')
        
        words = []
        current_time = 0.0
        current_word = ""
        word_start = current_time
        
        for char in mock_text:
            if char.isspace():
                continue
            elif char in punctuation:
                # 标点附加到当前词
                if current_word:
                    current_word += char
                    words.append(WordTimestamp(
                        word=current_word,
                        start_time=word_start,
                        end_time=current_time
                    ))
                    current_word = ""
                    current_time += 0.3  # 标点后停顿
            else:
                if current_word:
                    # 结束上一个词
                    words.append(WordTimestamp(
                        word=current_word,
                        start_time=word_start,
                        end_time=current_time
                    ))
                # 开始新词
                current_word = char
                word_start = current_time
                current_time += 0.25
        
        # 处理最后一个词
        if current_word:
            words.append(WordTimestamp(
                word=current_word,
                start_time=word_start,
                end_time=current_time
            ))
        
        return TranscriptionResult(
            text=mock_text,
            words=words,
            duration=current_time
        )


# 全局实例
_asr_service: Optional[ASRService] = None


def get_asr_service() -> ASRService:
    """获取ASR服务实例"""
    global _asr_service
    if _asr_service is None:
        _asr_service = ASRService()
    return _asr_service
