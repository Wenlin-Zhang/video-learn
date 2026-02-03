import React, { useEffect, useRef } from 'react';
import { SubtitleEntry } from '../types';

interface SubtitlePanelProps {
  subtitles: SubtitleEntry[];
  currentSubtitle: SubtitleEntry | null;
  onSubtitleClick: (subtitle: SubtitleEntry) => void;
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export const SubtitlePanel: React.FC<SubtitlePanelProps> = ({
  subtitles,
  currentSubtitle,
  onSubtitleClick,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const currentRef = useRef<HTMLDivElement>(null);

  // 自动滚动到当前字幕
  useEffect(() => {
    if (currentRef.current && containerRef.current) {
      const container = containerRef.current;
      const current = currentRef.current;
      
      const containerRect = container.getBoundingClientRect();
      const currentRect = current.getBoundingClientRect();
      
      // 检查是否在可视区域内
      if (currentRect.top < containerRect.top || currentRect.bottom > containerRect.bottom) {
        current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [currentSubtitle]);

  if (subtitles.length === 0) {
    return (
      <div className="subtitle-panel">
        <div className="panel-header">
          <h3>字幕</h3>
        </div>
        <div className="subtitle-empty">
          <p>暂无字幕数据</p>
        </div>
      </div>
    );
  }

  return (
    <div className="subtitle-panel">
      <div className="panel-header">
        <h3>字幕</h3>
        <span className="subtitle-count">{subtitles.length} 条</span>
      </div>
      <div className="subtitle-list" ref={containerRef}>
        {subtitles.map((subtitle) => (
          <div
            key={subtitle.index}
            ref={currentSubtitle?.index === subtitle.index ? currentRef : null}
            className={`subtitle-item ${currentSubtitle?.index === subtitle.index ? 'active' : ''}`}
            onClick={() => onSubtitleClick(subtitle)}
          >
            <span className="subtitle-time">
              {formatTime(subtitle.start_time)}
            </span>
            <span className="subtitle-text">{subtitle.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
