import React, { useState, useEffect } from 'react';
import { HistoryItem } from '../types';
import { getHistoryList, deleteHistory } from '../services/api';

interface HistoryListProps {
  onSelect: (item: HistoryItem) => void;
  onReprocess?: (item: HistoryItem) => void;
  onClose: () => void;
}

export const HistoryList: React.FC<HistoryListProps> = ({ onSelect, onReprocess, onClose }) => {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getHistoryList();
      setItems(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, taskId: string) => {
    e.stopPropagation();
    if (!confirm('确定要删除这条记录吗？相关文件也将被删除。')) {
      return;
    }

    setDeleting(taskId);
    try {
      await deleteHistory(taskId);
      setItems(items.filter(item => item.id !== taskId));
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除失败');
    } finally {
      setDeleting(null);
    }
  };

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

  // 从文件名中去除 UUID 后缀，返回纯净的文件名
  const stripTaskId = (filename: string): string => {
    // 去掉扩展名
    const dotIdx = filename.lastIndexOf('.');
    const stem = dotIdx > 0 ? filename.substring(0, dotIdx) : filename;
    const ext = dotIdx > 0 ? filename.substring(dotIdx) : '';
    // 匹配末尾的 _UUID 模式
    const uuidSuffix = /_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
    const cleaned = stem.replace(uuidSuffix, '');
    return cleaned + ext;
  };

  // 构建显示名称映射：重名时追加日期区分
  const getDisplayNames = (): Map<string, string> => {
    const nameMap = new Map<string, string>();
    // 按纯净名称分组
    const groups = new Map<string, HistoryItem[]>();
    for (const item of items) {
      const clean = stripTaskId(item.video_name);
      const group = groups.get(clean) || [];
      group.push(item);
      groups.set(clean, group);
    }
    for (const [clean, group] of groups) {
      if (group.length === 1) {
        nameMap.set(group[0].id, clean);
      } else {
        // 重名：追加日期区分
        for (const item of group) {
          const date = new Date(item.created_at);
          const suffix = date.toLocaleString('zh-CN', {
            month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit',
          });
          nameMap.set(item.id, `${clean} (${suffix})`);
        }
      }
    }
    return nameMap;
  };

  const displayNames = items.length > 0 ? getDisplayNames() : new Map<string, string>();

  return (
    <div className="history-overlay" onClick={onClose}>
      <div className="history-modal" onClick={e => e.stopPropagation()}>
        <div className="history-header">
          <h2>历史记录</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="history-content">
          {loading && <div className="history-loading">加载中...</div>}
          
          {error && <div className="history-error">{error}</div>}
          
          {!loading && !error && items.length === 0 && (
            <div className="history-empty">暂无历史记录</div>
          )}

          {!loading && !error && items.length > 0 && (
            <ul className="history-list">
              {items.map(item => (
                <li
                  key={item.id}
                  className="history-item"
                  onClick={() => onSelect(item)}
                >
                  <div className="history-item-main">
                    <div className="history-item-title">
                      {item.lecture_title || displayNames.get(item.id) || item.video_name}
                    </div>
                    <div className="history-item-info">
                      <span className="history-item-video">{displayNames.get(item.id) || item.video_name}</span>
                      <span className="history-item-duration">{formatDuration(item.duration)}</span>
                    </div>
                    <div className="history-item-date">{formatDate(item.created_at)}</div>
                  </div>
                  <div className="history-item-actions">
                    {onReprocess && (
                      <button
                        className="history-item-reprocess"
                        onClick={(e) => {
                          e.stopPropagation();
                          onReprocess(item);
                        }}
                        title="重新处理"
                      >
                        重新处理
                      </button>
                    )}
                    <button
                      className="history-item-delete"
                      onClick={(e) => handleDelete(e, item.id)}
                      disabled={deleting === item.id}
                    >
                      {deleting === item.id ? '...' : '删除'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};
