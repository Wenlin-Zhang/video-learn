import React from 'react';
import { getMarkdownExportUrl, getWordExportUrl, downloadFile } from '../services/api';

interface ExportButtonProps {
  taskId: string;
  lectureTitle: string;
  disabled?: boolean;
}

export const ExportButton: React.FC<ExportButtonProps> = ({ taskId, lectureTitle, disabled }) => {
  const [isExporting, setIsExporting] = React.useState(false);

  const handleExportMarkdown = async () => {
    setIsExporting(true);
    try {
      const url = getMarkdownExportUrl(taskId);
      await downloadFile(url, `${lectureTitle}.md`);
    } catch (error) {
      console.error('导出Markdown失败:', error);
      alert('导出失败，请重试');
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportWord = async () => {
    setIsExporting(true);
    try {
      const url = getWordExportUrl(taskId);
      await downloadFile(url, `${lectureTitle}.docx`);
    } catch (error) {
      console.error('导出Word失败:', error);
      alert('导出失败，请重试');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="export-buttons">
      <button
        className="export-btn markdown"
        onClick={handleExportMarkdown}
        disabled={disabled || isExporting}
      >
        {isExporting ? '导出中...' : '导出 Markdown'}
      </button>
      <button
        className="export-btn word"
        onClick={handleExportWord}
        disabled={disabled || isExporting}
      >
        {isExporting ? '导出中...' : '导出 Word'}
      </button>
    </div>
  );
};
