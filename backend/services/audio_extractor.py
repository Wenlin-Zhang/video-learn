"""音频提取服务 - 使用FFmpeg从视频中提取音频"""
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AudioExtractor:
    """音频提取器"""
    
    def __init__(self):
        self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> None:
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info("FFmpeg可用")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error("FFmpeg不可用，请确保已安装FFmpeg")
            raise RuntimeError("FFmpeg not found. Please install FFmpeg first.") from e
    
    def extract_audio(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        sample_rate: int = 16000,
        channels: int = 1
    ) -> str:
        """
        从视频文件提取音频
        
        Args:
            video_path: 视频文件路径
            output_path: 输出音频文件路径，如果不指定则自动生成
            sample_rate: 采样率，默认16kHz（适合语音识别）
            channels: 声道数，默认单声道
            
        Returns:
            输出音频文件路径
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        # 生成输出路径
        if output_path is None:
            output_path = video_path.with_suffix(".wav")
        else:
            output_path = Path(output_path)
        
        logger.info(f"开始从 {video_path} 提取音频到 {output_path}")
        
        # 使用FFmpeg提取音频
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",  # 不处理视频
            "-acodec", "pcm_s16le",  # 16位PCM编码
            "-ar", str(sample_rate),  # 采样率
            "-ac", str(channels),  # 声道数
            "-y",  # 覆盖已存在的文件
            str(output_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"音频提取成功: {output_path}")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            logger.error(f"音频提取失败: {e.stderr}")
            raise RuntimeError(f"Failed to extract audio: {e.stderr}") from e
    
    def get_video_duration(self, video_path: str) -> float:
        """
        获取视频时长（秒）
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频时长（秒）
        """
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            duration = float(result.stdout.strip())
            logger.info(f"视频时长: {duration:.2f}秒")
            return duration
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.error(f"获取视频时长失败: {e}")
            raise RuntimeError(f"Failed to get video duration: {e}") from e


# 全局实例
_extractor: Optional[AudioExtractor] = None


def get_audio_extractor() -> AudioExtractor:
    """获取音频提取器实例"""
    global _extractor
    if _extractor is None:
        _extractor = AudioExtractor()
    return _extractor
