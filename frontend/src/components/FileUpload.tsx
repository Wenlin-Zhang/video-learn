import React, { useRef, useState } from 'react';
import { HotWordsInput } from './HotWordsInput';

interface FileUploadProps {
  onFileSelect: (file: File, hotwords: string) => void;
  disabled?: boolean;
  accept?: string;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  onFileSelect,
  disabled = false,
  accept = 'video/*',
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [hotwords, setHotwords] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleClick = () => {
    inputRef.current?.click();
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('video/')) {
      setSelectedFile(file);
    } else {
      alert('请上传视频文件');
    }
  };

  const handleUpload = () => {
    if (selectedFile) {
      onFileSelect(selectedFile, hotwords);
    }
  };

  return (
    <div className="file-upload-container">
      {/* 文件拖拽/选择区域 */}
      <div
        className={`file-upload ${dragOver ? 'drag-over' : ''} ${disabled ? 'disabled' : ''}`}
        onClick={handleClick}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleChange}
          disabled={disabled}
          style={{ display: 'none' }}
        />
        <div className="upload-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        {selectedFile ? (
          <p className="upload-text selected-file">
            已选择: {selectedFile.name}
          </p>
        ) : (
          <p className="upload-text">
            {disabled ? '正在处理中...' : '点击或拖拽视频文件到这里'}
          </p>
        )}
        <p className="upload-hint">支持 MP4, AVI, MKV, MOV, WebM 等格式</p>
      </div>
      
      {/* 热词输入区域（独立在外） */}
      <div className="hotwords-section" onClick={(e) => e.stopPropagation()}>
        <HotWordsInput
          value={hotwords}
          onChange={setHotwords}
          placeholder="请输入热词，每行一个...&#10;例如：&#10;机器学习&#10;深度学习&#10;神经网络"
        />
      </div>
      
      {/* 上传按钮 */}
      {selectedFile && (
        <div className="upload-action">
          <button 
            className="upload-btn" 
            onClick={handleUpload}
            disabled={disabled}
          >
            上传视频
          </button>
        </div>
      )}
    </div>
  );
};
