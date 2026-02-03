"""VAD服务 - 使用silero-vad进行语音活动检测和音频切分

功能：
- 检测音频中的语音活动区间
- 将长音频切分为不超过指定时长的片段
- 在静音处智能切分，避免切断语音
"""
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Callable
from dataclasses import dataclass

import torch
import numpy as np
import soundfile as sf
import librosa

logger = logging.getLogger(__name__)


def load_audio(path: str, sampling_rate: int = 16000) -> torch.Tensor:
    """
    使用soundfile/librosa加载音频（替代silero_vad.read_audio以避免torchaudio版本问题）
    
    Args:
        path: 音频文件路径
        sampling_rate: 目标采样率
        
    Returns:
        音频数据tensor (1D, float32)
    """
    # 读取音频
    wav, sr = sf.read(path, dtype='float32')
    
    # 如果是多声道，转为单声道
    if len(wav.shape) > 1:
        wav = wav.mean(axis=1)
    
    # 如果采样率不同，重采样
    if sr != sampling_rate:
        wav = librosa.resample(wav, orig_sr=sr, target_sr=sampling_rate)
    
    return torch.from_numpy(wav)


@dataclass
class AudioSegment:
    """音频片段"""
    index: int
    start_time: float  # 秒
    end_time: float    # 秒
    file_path: Optional[str] = None  # 切分后的文件路径


class VADService:
    """VAD服务 - 使用silero-vad进行语音活动检测"""
    
    def __init__(
        self,
        max_segment_duration: float = 300.0,  # 最大片段时长（秒），默认5分钟
        min_silence_duration_ms: int = 500,   # 最小静音时长（毫秒）
        speech_threshold: float = 0.5,        # 语音检测阈值
        sample_rate: int = 16000,             # 采样率
    ):
        """
        初始化VAD服务
        
        Args:
            max_segment_duration: 最大片段时长（秒）
            min_silence_duration_ms: 用于分割的最小静音时长（毫秒）
            speech_threshold: 语音检测阈值
            sample_rate: 采样率
        """
        self.max_segment_duration = max_segment_duration
        self.min_silence_duration_ms = min_silence_duration_ms
        self.speech_threshold = speech_threshold
        self.sample_rate = sample_rate
        self._model = None
        
        logger.info(
            f"VAD服务初始化: max_segment={max_segment_duration}s, "
            f"min_silence={min_silence_duration_ms}ms, threshold={speech_threshold}"
        )
    
    def _load_model(self):
        """加载VAD模型"""
        if self._model is None:
            logger.info("加载silero-vad模型...")
            from silero_vad import load_silero_vad
            self._model = load_silero_vad()
            logger.info("VAD模型加载完成")
    
    def detect_speech(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> List[Tuple[float, float]]:
        """
        检测音频中的语音活动区间
        
        Args:
            audio_path: 音频文件路径
            progress_callback: 进度回调函数
            
        Returns:
            语音区间列表 [(start_time, end_time), ...]
        """
        self._load_model()
        
        from silero_vad import get_speech_timestamps
        
        logger.info(f"检测语音活动: {audio_path}")
        
        # 读取音频（使用自定义函数避免torchaudio版本问题）
        wav = load_audio(audio_path, sampling_rate=self.sample_rate)
        
        if progress_callback:
            progress_callback(30)
        
        # 检测语音时间戳
        speech_timestamps = get_speech_timestamps(
            wav,
            self._model,
            threshold=self.speech_threshold,
            sampling_rate=self.sample_rate,
            min_silence_duration_ms=self.min_silence_duration_ms,
            return_seconds=True,
        )
        
        if progress_callback:
            progress_callback(100)
        
        # 转换为时间区间列表
        segments = [(ts['start'], ts['end']) for ts in speech_timestamps]
        
        logger.info(f"检测到 {len(segments)} 个语音区间")
        return segments
    
    def segment_audio(
        self,
        audio_path: str,
        output_dir: str,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> List[AudioSegment]:
        """
        将长音频切分为不超过max_segment_duration的片段
        
        在静音处切分，避免切断语音。
        
        Args:
            audio_path: 输入音频文件路径
            output_dir: 输出目录
            progress_callback: 进度回调函数
            
        Returns:
            音频片段列表
        """
        audio_path = Path(audio_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_model()
        
        from silero_vad import get_speech_timestamps
        
        logger.info(f"开始切分音频: {audio_path}")
        
        # 读取音频（使用自定义函数避免torchaudio版本问题）
        wav = load_audio(str(audio_path), sampling_rate=self.sample_rate)
        total_duration = len(wav) / self.sample_rate
        
        logger.info(f"音频总时长: {total_duration:.1f}秒")
        
        if progress_callback:
            progress_callback(10)
        
        # 如果音频时长不超过最大限制，直接返回
        if total_duration <= self.max_segment_duration:
            logger.info("音频时长未超过限制，无需切分")
            return [AudioSegment(
                index=0,
                start_time=0.0,
                end_time=total_duration,
                file_path=str(audio_path)
            )]
        
        # 检测语音时间戳
        speech_timestamps = get_speech_timestamps(
            wav,
            self._model,
            threshold=self.speech_threshold,
            sampling_rate=self.sample_rate,
            min_silence_duration_ms=self.min_silence_duration_ms,
            return_seconds=True,
        )
        
        if progress_callback:
            progress_callback(30)
        
        # 计算切分点
        split_points = self._calculate_split_points(
            speech_timestamps, total_duration
        )
        
        logger.info(f"计算出 {len(split_points) - 1} 个切分点")
        
        # 切分音频并保存
        segments = []
        base_name = audio_path.stem
        
        for i in range(len(split_points) - 1):
            start_time = split_points[i]
            end_time = split_points[i + 1]
            
            start_sample = int(start_time * self.sample_rate)
            end_sample = int(end_time * self.sample_rate)
            
            segment_wav = wav[start_sample:end_sample].numpy()
            
            # 保存片段
            segment_path = output_dir / f"{base_name}_segment_{i:03d}.wav"
            sf.write(str(segment_path), segment_wav, self.sample_rate)
            
            segments.append(AudioSegment(
                index=i,
                start_time=start_time,
                end_time=end_time,
                file_path=str(segment_path)
            ))
            
            if progress_callback:
                progress = 30 + int(70 * (i + 1) / (len(split_points) - 1))
                progress_callback(progress)
        
        logger.info(f"音频切分完成，共 {len(segments)} 个片段")
        return segments
    
    def _calculate_split_points(
        self,
        speech_timestamps: List[dict],
        total_duration: float
    ) -> List[float]:
        """
        计算音频切分点
        
        在静音处切分，确保每个片段不超过max_segment_duration。
        
        Args:
            speech_timestamps: 语音时间戳列表
            total_duration: 音频总时长
            
        Returns:
            切分点列表（包括开始和结束）
        """
        max_duration = self.max_segment_duration
        split_points = [0.0]
        current_segment_start = 0.0
        
        # 找到所有静音区间
        silence_intervals = []
        prev_end = 0.0
        for ts in speech_timestamps:
            if ts['start'] > prev_end:
                silence_intervals.append((prev_end, ts['start']))
            prev_end = ts['end']
        if prev_end < total_duration:
            silence_intervals.append((prev_end, total_duration))
        
        # 在需要的位置切分
        for silence_start, silence_end in silence_intervals:
            silence_mid = (silence_start + silence_end) / 2
            
            # 如果当前片段时长超过限制，在静音处切分
            if silence_mid - current_segment_start > max_duration:
                # 在静音中点切分
                split_points.append(silence_mid)
                current_segment_start = silence_mid
        
        # 添加最后一个切分点
        if total_duration - current_segment_start > max_duration:
            # 如果最后一段还是太长，强制按时间切分
            while current_segment_start + max_duration < total_duration:
                current_segment_start += max_duration
                split_points.append(current_segment_start)
        
        split_points.append(total_duration)
        
        return split_points


# 全局实例
_vad_service: Optional[VADService] = None


def get_vad_service() -> VADService:
    """获取VAD服务实例"""
    global _vad_service
    if _vad_service is None:
        _vad_service = VADService()
    return _vad_service
