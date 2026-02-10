"""视频处理API路由"""
import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form, Query
from fastapi.responses import JSONResponse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from models.schemas import (
    VideoProcessResponse,
    SubtitleEntry,
    Section,
    Lecture,
    HistoryItem,
    HistoryList,
    ReprocessRequest,
    PipelineState,
)
from services.audio_extractor import get_audio_extractor
from services.asr_service import get_asr_service, extract_keywords_from_filename
from services.text_corrector import get_text_corrector
from services.subtitle_generator import SubtitleGenerator, parse_srt
from services.section_splitter import get_section_splitter
from services.lecture_generator import get_lecture_generator
from services.history_service import get_history_service
from services.intermediate_service import IntermediateService, StageStatus, STAGE_DEFINITIONS, get_stage_id
from routers.websocket import send_progress

logger = logging.getLogger(__name__)
router = APIRouter()

# 存储处理任务状态
processing_tasks = {}


async def process_video_task(
    task_id: str, 
    video_path: str, 
    output_dir: str, 
    user_hotwords: Optional[List[str]] = None,
    start_stage: str = "extract_audio"
):
    """
    后台视频处理任务（支持从任意阶段开始）
    
    Args:
        task_id: 任务ID
        video_path: 视频文件路径
        output_dir: 输出目录（视频同名文件夹）
        user_hotwords: 用户自定义热词列表
        start_stage: 起始阶段名称
    """
    try:
        processing_tasks[task_id] = {"status": "processing", "stage": "init"}
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        base_name = video_path.stem
        
        # 初始化中间结果服务
        intermediate = IntermediateService(str(output_dir))
        
        # 检查是否存在流程状态
        state = intermediate.load_pipeline_state()
        if state is None:
            # 首次处理，初始化流程状态
            state = intermediate.initialize_pipeline(
                task_id, video_path.name, str(video_path), user_hotwords
            )
        else:
            # 断点续处理，标记需要重新处理的阶段
            intermediate.mark_stages_for_reprocess(start_stage)
            # 如果提供了新的热词，更新
            if user_hotwords:
                state["hotwords"] = user_hotwords
                intermediate._save_state(state)
        
        # 获取起始阶段ID
        start_stage_id = get_stage_id(start_stage) or 1
        
        # 从文件名提取关键词作为动态热词（根据配置决定是否启用）
        config = get_config()
        filename_keywords = []
        if config.asr.extract_hotwords_from_filename:
            filename_keywords = extract_keywords_from_filename(video_path.name)
        
        # 合并热词
        combined_hotwords = []
        if user_hotwords:
            combined_hotwords.extend(user_hotwords)
        elif state and state.get("hotwords"):
            combined_hotwords.extend(state["hotwords"])
        if filename_keywords:
            combined_hotwords.extend(filename_keywords)
        
        loop = asyncio.get_event_loop()
        
        # ==================== 阶段1: 提取音频 ====================
        if start_stage_id <= 1:
            intermediate.update_stage_status("extract_audio", StageStatus.IN_PROGRESS)
            await send_progress(task_id, "extract_audio", 0, "正在提取音频...")
            processing_tasks[task_id]["stage"] = "extract_audio"
            
            extractor = get_audio_extractor()
            audio_path = output_dir / f"{base_name}.wav"
            
            await loop.run_in_executor(
                None, 
                extractor.extract_audio, 
                str(video_path), 
                str(audio_path)
            )
            
            duration = await loop.run_in_executor(
                None,
                extractor.get_video_duration,
                str(video_path)
            )
            
            # 使用VAD切分音频
            from services.vad_service import VADService
            
            segments_dir = output_dir / "segments"
            segments_dir.mkdir(parents=True, exist_ok=True)
            
            vad = VADService(max_segment_duration=300.0)
            audio_segments = await loop.run_in_executor(
                None,
                lambda: vad.segment_audio(str(audio_path), str(segments_dir))
            )
            
            # 保存阶段结果
            intermediate.save_stage_result("extract_audio", {
                "audio_path": str(audio_path),
                "duration": duration,
                "segments_dir": str(segments_dir),
                "segments": [
                    {
                        "index": seg.index,
                        "file_path": seg.file_path,
                        "start_time": seg.start_time,
                        "end_time": seg.end_time
                    }
                    for seg in audio_segments
                ]
            })
            intermediate.update_duration(duration)
            intermediate.update_stage_status("extract_audio", StageStatus.COMPLETED)
            
            await send_progress(task_id, "extract_audio", 100, "音频提取完成")
        else:
            # 加载已有结果
            stage1_data = intermediate.load_stage_result("extract_audio")
            if not stage1_data:
                raise RuntimeError("无法加载阶段1结果")
            audio_path = Path(stage1_data["audio_path"])
            duration = stage1_data["duration"]
            
            # 重建音频片段对象
            from services.vad_service import AudioSegment as VADSegment
            audio_segments = [
                VADSegment(
                    index=seg.get("index", i),
                    file_path=seg["file_path"],
                    start_time=seg["start_time"],
                    end_time=seg["end_time"]
                )
                for i, seg in enumerate(stage1_data["segments"])
            ]
        
        # ==================== 阶段2: 语音识别 ====================
        if start_stage_id <= 2:
            intermediate.update_stage_status("asr", StageStatus.IN_PROGRESS)
            await send_progress(task_id, "asr", 0, "正在进行语音识别...")
            processing_tasks[task_id]["stage"] = "asr"
            
            asr_service = get_asr_service()
            
            await send_progress(task_id, "asr", 20, f"音频切分完成，共 {len(audio_segments)} 个片段")
            
            # 逐片段识别
            segments_data = []
            for i, segment in enumerate(audio_segments):
                segment_progress = 20 + int(60 * (i + 1) / len(audio_segments))
                await send_progress(task_id, "asr", segment_progress, f"正在识别第 {i+1}/{len(audio_segments)} 段...")
                
                try:
                    segment_text = await loop.run_in_executor(
                        None,
                        lambda seg=segment: asr_service.transcribe_text_only(
                            seg.file_path,
                            extra_hotwords=combined_hotwords
                        )
                    )
                    
                    segments_data.append({
                        "segment_id": i,
                        "start_time": segment.start_time,
                        "end_time": segment.end_time,
                        "audio_file": segment.file_path,
                        "text": segment_text
                    })
                    
                except Exception as e:
                    logger.error(f"片段 {i+1} 识别失败: {e}")
                    segments_data.append({
                        "segment_id": i,
                        "start_time": segment.start_time,
                        "end_time": segment.end_time,
                        "audio_file": segment.file_path,
                        "text": ""
                    })
            
            # 保存阶段结果
            intermediate.save_stage_result("asr", {
                "segments_data": segments_data,
                "hotwords_used": combined_hotwords
            })
            intermediate.update_stage_status("asr", StageStatus.COMPLETED)
            
            await send_progress(task_id, "asr", 100, "语音识别完成")
        else:
            # 加载已有结果
            stage2_data = intermediate.load_stage_result("asr")
            if not stage2_data:
                raise RuntimeError("无法加载阶段2结果")
            segments_data = stage2_data["segments_data"]
        
        # ==================== 阶段3: 文本纠错 ====================
        if start_stage_id <= 3:
            intermediate.update_stage_status("text_correct", StageStatus.IN_PROGRESS)
            await send_progress(task_id, "text_correct", 0, "正在进行文本纠错...")
            processing_tasks[task_id]["stage"] = "text_correct"
            
            text_corrector = get_text_corrector()
            
            corrected_segments = await loop.run_in_executor(
                None,
                lambda: text_corrector.correct_segments_json(
                    segments_data,
                    hotwords=combined_hotwords
                )
            )
            
            # 保存阶段结果
            intermediate.save_stage_result("text_correct", {
                "corrected_segments": corrected_segments
            })
            intermediate.update_stage_status("text_correct", StageStatus.COMPLETED)
            
            await send_progress(task_id, "text_correct", 100, "文本纠错完成")
        else:
            # 加载已有结果
            stage3_data = intermediate.load_stage_result("text_correct")
            if not stage3_data:
                raise RuntimeError("无法加载阶段3结果")
            corrected_segments = stage3_data["corrected_segments"]
        
        # ==================== 阶段4: 时间对齐 ====================
        if start_stage_id <= 4:
            intermediate.update_stage_status("align", StageStatus.IN_PROGRESS)
            await send_progress(task_id, "align", 0, "正在进行时间对齐...")
            processing_tasks[task_id]["stage"] = "align"
            
            asr_service = get_asr_service()
            all_words = []
            
            for i, seg_data in enumerate(corrected_segments):
                segment_progress = int(80 * (i + 1) / len(corrected_segments))
                await send_progress(task_id, "align", segment_progress, f"正在对齐第 {i+1}/{len(corrected_segments)} 段...")
                
                corrected_text = seg_data.get("text", "")
                audio_file = seg_data.get("audio_file", "")
                segment_start = seg_data.get("start_time", 0.0)
                
                if corrected_text and audio_file:
                    try:
                        segment_words = await loop.run_in_executor(
                            None,
                            lambda af=audio_file, txt=corrected_text: asr_service.align_text(af, txt)
                        )
                        
                        for word in segment_words:
                            all_words.append({
                                "word": word.word,
                                "start_time": word.start_time + segment_start,
                                "end_time": word.end_time + segment_start
                            })
                            
                    except Exception as e:
                        logger.error(f"片段 {i+1} 对齐失败: {e}")
                        continue
            
            # 保存阶段结果
            intermediate.save_stage_result("align", {
                "words": all_words
            })
            intermediate.update_stage_status("align", StageStatus.COMPLETED)
            
            words = all_words
            await send_progress(task_id, "align", 100, "时间对齐完成")
        else:
            # 加载已有结果
            stage4_data = intermediate.load_stage_result("align")
            if not stage4_data:
                raise RuntimeError("无法加载阶段4结果")
            words = stage4_data["words"]
        
        # 将words转换为WordTimestamp对象
        from models.schemas import WordTimestamp
        word_objects = [
            WordTimestamp(word=w["word"], start_time=w["start_time"], end_time=w["end_time"])
            for w in words
        ]
        
        # ==================== 阶段5: 生成字幕 ====================
        if start_stage_id <= 5:
            intermediate.update_stage_status("subtitle", StageStatus.IN_PROGRESS)
            await send_progress(task_id, "subtitle", 0, "正在生成字幕...")
            processing_tasks[task_id]["stage"] = "subtitle"
            
            subtitle_generator = SubtitleGenerator()
            subtitle_entries = subtitle_generator.generate_entries(word_objects)
            
            srt_path = output_dir / f"{base_name}.srt"
            subtitle_generator.save_srt(subtitle_entries, str(srt_path))
            
            # 保存阶段结果
            intermediate.save_stage_result("subtitle", {
                "srt_path": str(srt_path),
                "subtitle_entries": [
                    {
                        "index": e.index,
                        "start_time": e.start_time,
                        "end_time": e.end_time,
                        "text": e.text
                    }
                    for e in subtitle_entries
                ]
            })
            intermediate.update_stage_status("subtitle", StageStatus.COMPLETED)
            
            await send_progress(task_id, "subtitle", 100, "字幕生成完成")
        else:
            # 加载已有结果
            stage5_data = intermediate.load_stage_result("subtitle")
            if not stage5_data:
                raise RuntimeError("无法加载阶段5结果")
            srt_path = Path(stage5_data["srt_path"])
            subtitle_entries = [
                SubtitleEntry(**e) for e in stage5_data["subtitle_entries"]
            ]
        
        # ==================== 阶段6: 小节划分 ====================
        if start_stage_id <= 6:
            intermediate.update_stage_status("section_split", StageStatus.IN_PROGRESS)
            await send_progress(task_id, "section_split", 0, "正在划分小节...")
            processing_tasks[task_id]["stage"] = "section_split"
            
            splitter = get_section_splitter()
            section_info = await loop.run_in_executor(
                None,
                lambda: splitter.split_sections(subtitle_entries)
            )
            
            sections = splitter.create_sections_with_time(section_info, subtitle_entries)
            
            # 保存阶段结果
            intermediate.save_stage_result("section_split", {
                "sections": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "content": s.content,
                        "summary": s.summary
                    }
                    for s in sections
                ]
            })
            intermediate.update_stage_status("section_split", StageStatus.COMPLETED)
            
            await send_progress(task_id, "section_split", 100, "小节划分完成")
        else:
            # 加载已有结果
            stage6_data = intermediate.load_stage_result("section_split")
            if not stage6_data:
                raise RuntimeError("无法加载阶段6结果")
            sections = [Section(**s) for s in stage6_data["sections"]]
        
        # ==================== 阶段7: 生成讲义 ====================
        if start_stage_id <= 7:
            intermediate.update_stage_status("lecture_gen", StageStatus.IN_PROGRESS)
            await send_progress(task_id, "lecture_gen", 0, "正在生成讲义...")
            processing_tasks[task_id]["stage"] = "lecture_gen"
            
            lecture_gen = get_lecture_generator()
            
            lecture = await loop.run_in_executor(
                None,
                lambda: lecture_gen.generate_lecture(
                    sections,
                    video_path.name,
                    duration
                )
            )
            
            lecture_path = output_dir / f"{base_name}.json"
            lecture_gen.save_lecture(lecture, str(lecture_path))
            
            # 保存阶段结果
            intermediate.save_stage_result("lecture_gen", {
                "lecture_path": str(lecture_path),
                "lecture_title": lecture.title
            })
            intermediate.update_stage_status("lecture_gen", StageStatus.COMPLETED)
            
            await send_progress(task_id, "lecture_gen", 100, "讲义生成完成")
        else:
            # 加载已有结果
            stage7_data = intermediate.load_stage_result("lecture_gen")
            if not stage7_data:
                raise RuntimeError("无法加载阶段7结果")
            lecture_path = Path(stage7_data["lecture_path"])
            lecture_gen = get_lecture_generator()
            lecture = lecture_gen.load_lecture(str(lecture_path))
        
        # 添加到历史记录
        history_service = get_history_service()
        history_service.add(
            task_id=task_id,
            video_name=video_path.name,
            video_path=str(video_path),
            output_dir=str(output_dir),
            srt_path=str(srt_path),
            lecture_path=str(lecture_path),
            duration=duration,
            lecture_title=lecture.title
        )
        
        # 完成
        processing_tasks[task_id] = {
            "status": "completed",
            "stage": "done",
            "result": {
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "srt_path": str(srt_path),
                "lecture_path": str(lecture_path),
                "output_dir": str(output_dir),
                "duration": duration
            }
        }
        
        await send_progress(task_id, "done", 100, "处理完成")
        logger.info(f"任务 {task_id} 处理完成，输出目录: {output_dir}")
        
    except Exception as e:
        logger.error(f"任务 {task_id} 处理失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 更新失败状态
        if 'intermediate' in locals():
            current_stage = processing_tasks.get(task_id, {}).get("stage", "unknown")
            intermediate.update_stage_status(current_stage, StageStatus.FAILED, str(e))
        
        processing_tasks[task_id] = {
            "status": "failed",
            "stage": "error",
            "error": str(e)
        }
        await send_progress(task_id, "error", 0, f"处理失败: {e}")


@router.get("/check-duplicate")
async def check_duplicate(filename: str):
    """
    检查是否已有同名视频的处理记录
    
    Args:
        filename: 原始文件名
        
    Returns:
        重复检测结果
    """
    history_service = get_history_service()
    duplicates = history_service.find_by_original_name(filename)
    return {
        "has_duplicate": len(duplicates) > 0,
        "duplicates": [
            {
                "id": item.id,
                "video_name": item.video_name,
                "lecture_title": item.lecture_title,
                "created_at": item.created_at.isoformat(),
                "duration": item.duration,
            }
            for item in duplicates
        ]
    }


@router.post("/upload", response_model=VideoProcessResponse)
async def upload_video(
    file: UploadFile = File(...),
    overwrite_task_id: Optional[str] = Form(None)
):
    """
    上传视频文件（不开始处理）
    
    Args:
        file: 视频文件
        overwrite_task_id: 可选，覆盖已有任务的 ID（删除旧文件并复用 UUID）
        
    Returns:
        处理任务信息
    """
    # 验证文件类型
    allowed_extensions = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}，支持的格式: {', '.join(allowed_extensions)}"
        )
    
    config = get_config()
    
    # 覆盖模式：删除旧文件，复用旧 task_id
    if overwrite_task_id:
        history_service = get_history_service()
        old_item = history_service.get(overwrite_task_id)
        if not old_item:
            raise HTTPException(status_code=404, detail="要覆盖的任务不存在")
        # 删除旧文件和历史记录
        history_service.delete(overwrite_task_id, delete_files=True)
        task_id = overwrite_task_id
    else:
        task_id = str(uuid.uuid4())
    
    # 保存上传的文件
    upload_dir = Path(config.storage.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    video_path = upload_dir / f"{Path(file.filename).stem}_{task_id}{Path(file.filename).suffix}"
    
    with open(video_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    logger.info(f"视频文件已上传: {video_path}")
    
    # 输出目录放到 outputs/ 中
    output_dir = Path(config.storage.output_dir) / video_path.stem
    
    # 保存任务状态（待处理状态）
    processing_tasks[task_id] = {
        "status": "uploaded",
        "stage": "init",
        "video_path": str(video_path),
        "output_dir": str(output_dir)
    }
    
    return VideoProcessResponse(
        task_id=task_id,
        status="uploaded",
        message="视频上传成功，等待处理"
    )


@router.post("/start/{task_id}", response_model=VideoProcessResponse)
async def start_processing(
    background_tasks: BackgroundTasks,
    task_id: str,
    hotwords: Optional[str] = Form(None)
):
    """
    开始处理已上传的视频
    
    Args:
        task_id: 任务ID
        hotwords: 用户自定义热词列表，以换行符分隔
        
    Returns:
        处理任务信息
    """
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = processing_tasks[task_id]
    
    if task["status"] not in ["uploaded", "pending"]:
        raise HTTPException(status_code=400, detail=f"任务状态不正确: {task['status']}")
    
    video_path = task.get("video_path")
    output_dir = task.get("output_dir")
    
    if not video_path or not output_dir:
        raise HTTPException(status_code=400, detail="任务信息不完整")
    
    # 解析用户自定义热词
    user_hotwords = []
    if hotwords:
        user_hotwords = [word.strip() for word in hotwords.split('\n') if word.strip()]
        logger.info(f"用户自定义热词: {user_hotwords}")
    
    # 更新任务状态
    processing_tasks[task_id]["status"] = "pending"
    processing_tasks[task_id]["stage"] = "init"
    
    # 启动后台处理任务
    background_tasks.add_task(process_video_task, task_id, video_path, output_dir, user_hotwords)
    
    return VideoProcessResponse(
        task_id=task_id,
        status="pending",
        message="开始处理视频"
    )


@router.post("/process", response_model=VideoProcessResponse)
async def process_local_video(
    background_tasks: BackgroundTasks,
    video_path: str,
    hotwords: Optional[str] = Query(None)  # 用户自定义热词，以换行符分隔
):
    """
    处理本地视频文件
    
    Args:
        video_path: 本地视频文件路径
        hotwords: 用户自定义热词列表，以换行符分隔
        
    Returns:
        处理任务信息
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"视频文件不存在: {video_path}")
    
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 解析用户自定义热词
    user_hotwords = []
    if hotwords:
        # 按换行符分割，并去除空白行和空格
        user_hotwords = [word.strip() for word in hotwords.split('\n') if word.strip()]
        logger.info(f"用户自定义热词: {user_hotwords}")
    
    # 输出目录放到 outputs/ 中
    config = get_config()
    output_dir = Path(config.storage.output_dir) / f"{video_path.stem}_{task_id}"
    
    # 启动后台处理任务
    processing_tasks[task_id] = {"status": "pending", "stage": "init"}
    background_tasks.add_task(process_video_task, task_id, str(video_path), str(output_dir), user_hotwords)
    
    return VideoProcessResponse(
        task_id=task_id,
        status="pending",
        message="开始处理视频"
    )


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    获取任务状态
    
    Args:
        task_id: 任务ID
        
    Returns:
        任务状态信息
    """
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return processing_tasks[task_id]


@router.get("/result/{task_id}")
async def get_task_result(task_id: str):
    """
    获取任务结果
    
    Args:
        task_id: 任务ID
        
    Returns:
        处理结果，包含字幕和讲义数据
    """
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = processing_tasks[task_id]
    
    if task["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"任务尚未完成，当前状态: {task['status']}"
        )
    
    result = task["result"]
    
    # 读取字幕文件
    subtitles = parse_srt(result["srt_path"])
    
    # 读取讲义文件
    lecture_gen = get_lecture_generator()
    lecture = lecture_gen.load_lecture(result["lecture_path"])
    
    return {
        "task_id": task_id,
        "video_path": result["video_path"],
        "duration": result["duration"],
        "subtitles": [s.model_dump() for s in subtitles],
        "lecture": lecture.model_dump(mode="json")
    }


@router.get("/subtitles/{task_id}")
async def get_subtitles(task_id: str):
    """获取字幕数据"""
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = processing_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    subtitles = parse_srt(task["result"]["srt_path"])
    return {"subtitles": [s.model_dump() for s in subtitles]}


@router.get("/lecture/{task_id}")
async def get_lecture(task_id: str):
    """获取讲义数据"""
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = processing_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    lecture_gen = get_lecture_generator()
    lecture = lecture_gen.load_lecture(task["result"]["lecture_path"])
    return lecture.model_dump(mode="json")


# ==================== 历史记录API ====================

@router.get("/history", response_model=HistoryList)
async def get_history(limit: int = 50, offset: int = 0):
    """
    获取历史记录列表
    
    Args:
        limit: 返回数量限制
        offset: 偏移量
        
    Returns:
        历史记录列表
    """
    history_service = get_history_service()
    return history_service.list(limit=limit, offset=offset)


@router.get("/history/{task_id}", response_model=HistoryItem)
async def get_history_item(task_id: str):
    """
    获取单条历史记录
    
    Args:
        task_id: 任务ID
        
    Returns:
        历史记录项
    """
    history_service = get_history_service()
    item = history_service.get(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return item


@router.get("/history/{task_id}/load")
async def load_history_result(task_id: str):
    """
    加载历史记录的处理结果（字幕和讲义）
    
    Args:
        task_id: 任务ID
        
    Returns:
        处理结果，包含字幕和讲义数据
    """
    history_service = get_history_service()
    item = history_service.get(task_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    
    # 验证文件是否存在
    if not history_service.validate(task_id):
        raise HTTPException(status_code=404, detail="历史文件已被删除或损坏")
    
    # 读取字幕文件
    subtitles = parse_srt(item.srt_path)
    
    # 读取讲义文件
    lecture_gen = get_lecture_generator()
    lecture = lecture_gen.load_lecture(item.lecture_path)
    
    return {
        "task_id": task_id,
        "video_path": item.video_path,
        "video_name": item.video_name,
        "duration": item.duration,
        "subtitles": [s.model_dump() for s in subtitles],
        "lecture": lecture.model_dump(mode="json")
    }


@router.delete("/history/{task_id}")
async def delete_history(task_id: str, delete_files: bool = True):
    """
    删除历史记录
    
    Args:
        task_id: 任务ID
        delete_files: 是否同时删除文件，默认为True
        
    Returns:
        删除结果
    """
    history_service = get_history_service()
    
    if not history_service.exists(task_id):
        raise HTTPException(status_code=404, detail="历史记录不存在")
    
    success = history_service.delete(task_id, delete_files=delete_files)
    
    if success:
        # 同时清理内存中的任务状态
        if task_id in processing_tasks:
            del processing_tasks[task_id]
        return {"message": "删除成功", "task_id": task_id}
    else:
        raise HTTPException(status_code=500, detail="删除失败")


# ==================== 流程状态和重新处理API ====================

@router.get("/pipeline/{task_id}/state")
async def get_pipeline_state(task_id: str):
    """
    获取处理流程状态（包含所有阶段的完成情况）
    
    Args:
        task_id: 任务ID
        
    Returns:
        流程状态信息
    """
    history_service = get_history_service()
    item = history_service.get(task_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    intermediate = IntermediateService(item.output_dir)
    state = intermediate.load_pipeline_state()
    
    if not state:
        # 为旧的历史记录创建回退状态
        logger.info(f"为旧历史记录 {task_id} 创建回退流程状态")
        state = intermediate.initialize_pipeline(
            task_id=task_id,
            video_name=item.video_name,
            video_path=item.video_path,
            hotwords=[],
            duration=item.duration
        )
        # 检查每个阶段的中间结果文件是否存在，存在则标记为完成
        for stage in state["stages"]:
            result_file = intermediate.intermediate_dir / f"stage_{stage['stage_id']}_{stage['stage_name']}.json"
            if result_file.exists():
                stage["status"] = StageStatus.COMPLETED.value
                stage["completed_at"] = item.created_at
                stage["result_file"] = result_file.name
            else:
                # 文件不存在，保持 pending 状态
                stage["status"] = StageStatus.PENDING.value
        intermediate._save_state(state)
    
    return state


@router.post("/reprocess/{task_id}", response_model=VideoProcessResponse)
async def reprocess_video(
    background_tasks: BackgroundTasks,
    task_id: str,
    request: ReprocessRequest
):
    """
    从指定阶段重新处理视频
    
    Args:
        task_id: 任务ID（必须是历史记录中存在的任务）
        request: 包含start_stage（起始阶段名称）和可选的hotwords
    
    Returns:
        处理任务信息
    """
    history_service = get_history_service()
    item = history_service.get(task_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    
    # 验证阶段名称
    valid_stages = [stage["name"] for stage in STAGE_DEFINITIONS]
    if request.start_stage not in valid_stages:
        raise HTTPException(
            status_code=400, 
            detail=f"无效的阶段名称，有效值为: {', '.join(valid_stages)}"
        )
    
    # 检查是否可以从该阶段开始
    intermediate = IntermediateService(item.output_dir)
    if not intermediate.can_start_from_stage(request.start_stage):
        raise HTTPException(
            status_code=400,
            detail="前置阶段未完成，无法从该阶段开始"
        )
    
    # 更新任务状态
    processing_tasks[task_id] = {"status": "pending", "stage": "init"}
    
    # 启动后台处理任务
    background_tasks.add_task(
        process_video_task,
        task_id,
        item.video_path,
        item.output_dir,
        request.hotwords,
        request.start_stage
    )
    
    return VideoProcessResponse(
        task_id=task_id,
        status="pending",
        message=f"开始从阶段 {request.start_stage} 重新处理"
    )


@router.get("/pipeline/{task_id}/stage/{stage_name}")
async def get_stage_result(task_id: str, stage_name: str):
    """
    获取指定阶段的中间结果
    
    Args:
        task_id: 任务ID
        stage_name: 阶段名称
        
    Returns:
        阶段结果数据
    """
    history_service = get_history_service()
    item = history_service.get(task_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    intermediate = IntermediateService(item.output_dir)
    result = intermediate.load_stage_result(stage_name)
    
    if not result:
        raise HTTPException(status_code=404, detail="阶段结果不存在")
    
    return result
