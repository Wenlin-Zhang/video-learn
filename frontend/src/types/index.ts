// 字幕条目
export interface SubtitleEntry {
  index: number;
  start_time: number;
  end_time: number;
  text: string;
}

// 讲义小节
export interface Section {
  id: number;
  title: string;
  start_time: number;
  end_time: number;
  content: string;
  summary: string;
}

// 讲义元数据
export interface LectureMetadata {
  video_file: string;
  duration: number;
  created_at: string;
}

// 完整讲义
export interface Lecture {
  title: string;
  sections: Section[];
  metadata: LectureMetadata;
}

// 处理阶段
export interface ProcessingStage {
  name: string;
  label: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress: number;
}

// 处理进度消息
export interface ProgressMessage {
  task_id: string;
  stage: string;
  progress: number;
  message: string;
  stages: ProcessingStage[];
}

// 任务状态
export interface TaskStatus {
  status: 'pending' | 'processing' | 'completed' | 'failed';
  stage: string;
  result?: TaskResult;
  error?: string;
}

// 任务结果
export interface TaskResult {
  video_path: string;
  audio_path: string;
  srt_path: string;
  lecture_path: string;
  duration: number;
}

// 完整结果数据
export interface ResultData {
  task_id: string;
  video_path: string;
  video_name?: string;
  duration: number;
  subtitles: SubtitleEntry[];
  lecture: Lecture;
}

// 历史记录项
export interface HistoryItem {
  id: string;
  video_name: string;
  video_path: string;
  output_dir: string;
  srt_path: string;
  lecture_path: string;
  duration: number;
  created_at: string;
  lecture_title?: string;
}

// 历史记录列表
export interface HistoryList {
  items: HistoryItem[];
  total: number;
}

// 阶段状态
export type StageStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

// 阶段信息（流程状态中使用）
export interface StageInfo {
  stage_id: number;
  stage_name: string;
  stage_label: string;
  status: StageStatus;
  started_at?: string;
  completed_at?: string;
  result_file?: string;
  error?: string;
}

// 流程状态
export interface PipelineState {
  task_id: string;
  video_name: string;
  video_path: string;
  output_dir: string;
  created_at: string;
  updated_at: string;
  duration?: number;
  stages: StageInfo[];
  hotwords?: string[];
  metadata?: Record<string, unknown>;
}

// 重新处理请求
export interface ReprocessRequest {
  start_stage: string;
  hotwords?: string[];
}
