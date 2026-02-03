import React from 'react';
import { ProcessingStage } from '../types';

interface ProgressBarProps {
  stages: ProcessingStage[];
  currentMessage: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ stages, currentMessage }) => {
  // 计算总体进度
  const completedStages = stages.filter(s => s.status === 'completed').length;
  const currentStage = stages.find(s => s.status === 'in_progress');
  const totalProgress = stages.length > 0 
    ? ((completedStages + (currentStage ? currentStage.progress / 100 : 0)) / stages.length) * 100
    : 0;

  // 格式化进度百分比
  const formatProgress = (progress: number) => {
    return progress > 0 ? `${Math.round(progress)}%` : '';
  };

  return (
    <div className="progress-container">
      <div className="progress-header">
        <div className="progress-message">{currentMessage}</div>
        <div className="progress-percentage">{Math.round(totalProgress)}%</div>
      </div>
      
      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ width: `${totalProgress}%` }}
        />
      </div>
      
      <div className="progress-stages">
        {stages.map((stage, index) => (
          <div
            key={stage.name}
            className={`stage-item ${stage.status}`}
          >
            <div className="stage-connector">
              {index > 0 && <div className={`connector-line ${stages[index - 1].status === 'completed' ? 'completed' : ''}`} />}
            </div>
            <div className="stage-indicator">
              {stage.status === 'completed' && <span className="check">&#10003;</span>}
              {stage.status === 'in_progress' && <span className="spinner" />}
              {stage.status === 'failed' && <span className="error">&#10007;</span>}
              {stage.status === 'pending' && <span className="dot">{index + 1}</span>}
            </div>
            <div className="stage-info">
              <div className="stage-label">{stage.label}</div>
              {stage.status === 'in_progress' && (
                <>
                  <div className="stage-progress-bar">
                    <div className="stage-progress-fill" style={{ width: `${stage.progress}%` }} />
                  </div>
                  <div className="stage-progress">{formatProgress(stage.progress)}</div>
                </>
              )}
              {stage.status === 'completed' && (
                <div className="stage-completed-text">完成</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
