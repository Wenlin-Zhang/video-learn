import { ResultData, HistoryList, HistoryItem, PipelineState, ReprocessRequest } from '../types';

const API_BASE = '/api';

// 检查是否有同名视频的处理记录
export interface DuplicateInfo {
  id: string;
  video_name: string;
  lecture_title: string | null;
  created_at: string;
  duration: number;
}

export interface DuplicateCheckResult {
  has_duplicate: boolean;
  duplicates: DuplicateInfo[];
}

export async function checkDuplicate(filename: string): Promise<DuplicateCheckResult> {
  const response = await fetch(`${API_BASE}/video/check-duplicate?filename=${encodeURIComponent(filename)}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '检查重复失败');
  }

  return response.json();
}

// 上传视频（不开始处理）
export async function uploadVideo(file: File, overwriteTaskId?: string): Promise<{ task_id: string; status: string; message: string }> {
  const formData = new FormData();
  formData.append('file', file);
  if (overwriteTaskId) {
    formData.append('overwrite_task_id', overwriteTaskId);
  }

  const response = await fetch(`${API_BASE}/video/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '上传失败');
  }

  return response.json();
}

// 开始处理视频
export async function startProcessing(taskId: string, hotwords?: string): Promise<{ task_id: string; status: string; message: string }> {
  const options: RequestInit = { method: 'POST' };

  if (hotwords) {
    const formData = new FormData();
    formData.append('hotwords', hotwords);
    options.body = formData;
  }

  const response = await fetch(`${API_BASE}/video/start/${taskId}`, options);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '启动处理失败');
  }

  return response.json();
}

// 处理本地视频
export async function processLocalVideo(videoPath: string): Promise<{ task_id: string; status: string; message: string }> {
  const response = await fetch(`${API_BASE}/video/process?video_path=${encodeURIComponent(videoPath)}`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '处理请求失败');
  }

  return response.json();
}

// 获取任务状态
export async function getTaskStatus(taskId: string): Promise<{ status: string; stage: string; result?: any; error?: string }> {
  const response = await fetch(`${API_BASE}/video/status/${taskId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '获取状态失败');
  }

  return response.json();
}

// 获取任务结果
export async function getTaskResult(taskId: string): Promise<ResultData> {
  const response = await fetch(`${API_BASE}/video/result/${taskId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '获取结果失败');
  }

  return response.json();
}

// 导出Markdown
export function getMarkdownExportUrl(taskId: string): string {
  return `${API_BASE}/export/markdown/${taskId}`;
}

// 导出Word
export function getWordExportUrl(taskId: string): string {
  return `${API_BASE}/export/word/${taskId}`;
}

// 下载文件
export async function downloadFile(url: string, filename: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error('下载失败');
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);
}

// ==================== 历史记录API ====================

// 获取历史记录列表
export async function getHistoryList(limit: number = 50, offset: number = 0): Promise<HistoryList> {
  const response = await fetch(`${API_BASE}/video/history?limit=${limit}&offset=${offset}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '获取历史记录失败');
  }

  return response.json();
}

// 获取单条历史记录
export async function getHistoryItem(taskId: string): Promise<HistoryItem> {
  const response = await fetch(`${API_BASE}/video/history/${taskId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '获取历史记录失败');
  }

  return response.json();
}

// 加载历史记录结果
export async function loadHistoryResult(taskId: string): Promise<ResultData> {
  const response = await fetch(`${API_BASE}/video/history/${taskId}/load`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '加载历史记录失败');
  }

  return response.json();
}

// 删除历史记录
export async function deleteHistory(taskId: string, deleteFiles: boolean = true): Promise<{ message: string; task_id: string }> {
  const response = await fetch(`${API_BASE}/video/history/${taskId}?delete_files=${deleteFiles}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '删除失败');
  }

  return response.json();
}

// ==================== 流程状态和重新处理API ====================

// 获取流程状态
export async function getPipelineState(taskId: string): Promise<PipelineState> {
  const response = await fetch(`${API_BASE}/video/pipeline/${taskId}/state`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '获取流程状态失败');
  }

  return response.json();
}

// 从指定阶段重新处理
export async function reprocessVideo(
  taskId: string, 
  request: ReprocessRequest
): Promise<{ task_id: string; status: string; message: string }> {
  const response = await fetch(`${API_BASE}/video/reprocess/${taskId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '重新处理失败');
  }

  return response.json();
}

// 获取阶段结果
export async function getStageResult(taskId: string, stageName: string): Promise<unknown> {
  const response = await fetch(`${API_BASE}/video/pipeline/${taskId}/stage/${stageName}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '获取阶段结果失败');
  }

  return response.json();
}
