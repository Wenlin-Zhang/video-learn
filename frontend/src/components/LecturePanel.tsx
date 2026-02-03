import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Section } from '../types';

interface LecturePanelProps {
  sections: Section[];
  currentSection: Section | null;
  onSectionClick: (section: Section) => void;
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * 清理Markdown内容中不必要的外层代码块包装
 * LLM有时会将整个Markdown内容包裹在 ```markdown...``` 中
 */
function cleanMarkdownContent(content: string): string {
  if (!content) return '';
  
  let cleaned = content.trim();
  
  // 匹配并移除开头的 ```markdown 或 ```md 或 ``` 标记
  const startPattern = /^```(?:markdown|md)?\s*\n/i;
  // 匹配并移除结尾的 ``` 标记
  const endPattern = /\n```\s*$/;
  
  if (startPattern.test(cleaned) && endPattern.test(cleaned)) {
    cleaned = cleaned.replace(startPattern, '').replace(endPattern, '');
  }
  
  return cleaned.trim();
}

export const LecturePanel: React.FC<LecturePanelProps> = ({
  sections,
  currentSection,
  onSectionClick,
}) => {
  const currentRef = useRef<HTMLDivElement>(null);

  // 自动滚动到当前小节
  useEffect(() => {
    if (currentRef.current) {
      currentRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [currentSection]);

  if (sections.length === 0) {
    return (
      <div className="lecture-panel">
        <div className="panel-header">
          <h3>讲义</h3>
        </div>
        <div className="lecture-empty">
          <p>暂无讲义数据</p>
        </div>
      </div>
    );
  }

  return (
    <div className="lecture-panel">
      <div className="panel-header">
        <h3>讲义</h3>
        <div className="header-controls">
          <select 
            className="section-selector"
            value={currentSection?.id || ''}
            onChange={(e) => {
              const section = sections.find(s => s.id === Number(e.target.value));
              if (section) onSectionClick(section);
            }}
          >
            <option value="">跳转到...</option>
            {sections.map(s => (
              <option key={s.id} value={s.id}>
                {s.id}. {s.title}
              </option>
            ))}
          </select>
          <span className="section-count">{sections.length} 个小节</span>
        </div>
      </div>
      <div className="section-list vertical">
        {sections.map((section) => (
          <div
            key={section.id}
            ref={currentSection?.id === section.id ? currentRef : null}
            className={`section-item ${currentSection?.id === section.id ? 'active' : ''}`}
            onClick={() => onSectionClick(section)}
          >
            <div className="section-header">
              <span className="section-number">{section.id}</span>
              <span className="section-title">{section.title}</span>
              <span className="section-time">
                {formatTime(section.start_time)} - {formatTime(section.end_time)}
              </span>
            </div>
            <div className="section-content markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {cleanMarkdownContent(section.content)}
              </ReactMarkdown>
            </div>
            {section.summary && (
              <div className="section-summary">
                <strong>摘要:</strong> {section.summary}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
