import React from 'react';

interface HotWordsInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
}

export const HotWordsInput: React.FC<HotWordsInputProps> = ({
  value,
  onChange,
  placeholder = '请输入热词，每行一个...',
  label = '热词列表（可选）',
}) => {
  return (
    <div className="hotwords-input">
      <label className="hotwords-label">{label}</label>
      <textarea
        className="hotwords-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={4}
      />
      <div className="hotwords-hint">
        每行输入一个热词，支持专业术语、人名、地名等，将提升识别准确率
      </div>
    </div>
  );
};