import React from 'react';
import { DuplicateInfo } from '../services/api';

interface DuplicateDialogProps {
  filename: string;
  duplicates: DuplicateInfo[];
  onCancel: (openTaskId?: string) => void;
  onOverwrite: (taskId: string) => void;
  onNewUpload: () => void;
}

export const DuplicateDialog: React.FC<DuplicateDialogProps> = ({
  filename,
  duplicates,
  onCancel,
  onOverwrite,
  onNewUpload,
}) => {
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="duplicate-overlay" onClick={() => onCancel()}>
      <div className="duplicate-modal" onClick={e => e.stopPropagation()}>
        <div className="duplicate-header">
          <h3>检测到同名视频</h3>
          <button className="close-btn" onClick={() => onCancel()}>&times;</button>
        </div>

        <div className="duplicate-body">
          <p className="duplicate-message">
            文件 <strong>{filename}</strong> 已有处理记录：
          </p>

          <ul className="duplicate-list">
            {duplicates.map(item => (
              <li key={item.id} className="duplicate-item">
                <span className="duplicate-item-title">
                  {item.lecture_title || item.video_name}
                </span>
                <span className="duplicate-item-info">
                  {formatDuration(item.duration)} | {formatDate(item.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="duplicate-actions">
          <button
            className="duplicate-btn duplicate-btn-cancel"
            onClick={() => {
              const open = window.confirm('是否打开已处理的视频结果？');
              onCancel(open ? duplicates[0].id : undefined);
            }}
          >
            放弃上传
          </button>
          <button
            className="duplicate-btn duplicate-btn-overwrite"
            onClick={() => onOverwrite(duplicates[0].id)}
          >
            覆盖处理
          </button>
          <button className="duplicate-btn duplicate-btn-new" onClick={onNewUpload}>
            新建处理
          </button>
        </div>
      </div>
    </div>
  );
};
