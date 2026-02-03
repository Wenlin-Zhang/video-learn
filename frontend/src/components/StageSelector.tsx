import React, { useState, useEffect } from 'react';
import { PipelineState, StageInfo } from '../types';
import { getPipelineState, reprocessVideo } from '../services/api';
import './StageSelector.css';

interface StageSelectorProps {
  taskId: string;
  onReprocess: (taskId: string, startStage: string, videoPath: string) => void;
  onClose: () => void;
}

export const StageSelector: React.FC<StageSelectorProps> = ({ 
  taskId, 
  onReprocess, 
  onClose 
}) => {
  const [loading, setLoading] = useState(true);
  const [pipelineState, setPipelineState] = useState<PipelineState | null>(null);
  const [selectedStage, setSelectedStage] = useState<string>('');
  const [hotwords, setHotwords] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [reprocessing, setReprocessing] = useState(false);

  useEffect(() => {
    loadPipelineState();
  }, [taskId]);

  const loadPipelineState = async () => {
    setLoading(true);
    setError(null);
    try {
      const state = await getPipelineState(taskId);
      setPipelineState(state);
      
      // 默认选择第一个已完成的阶段
      const firstCompleted = state.stages.find(s => s.status === 'completed');
      if (firstCompleted) {
        setSelectedStage(firstCompleted.stage_name);
      }
      
      // 预填充热词
      if (state.hotwords) {
        setHotwords(state.hotwords.join('\n'));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const handleReprocess = async () => {
    if (!selectedStage) {
      alert('请选择起始阶段');
      return;
    }

    const stageLabel = getStageLabel(selectedStage);
    if (!confirm(`确定要从"${stageLabel}"阶段重新处理吗？该阶段及后续阶段的结果将被覆盖。`)) {
      return;
    }

    setReprocessing(true);
    setError(null);

    try {
      const hotwordsList = hotwords
        .split('\n')
        .map(w => w.trim())
        .filter(w => w.length > 0);

      await reprocessVideo(taskId, {
        start_stage: selectedStage,
        hotwords: hotwordsList.length > 0 ? hotwordsList : undefined,
      });

      onReprocess(taskId, selectedStage, pipelineState?.video_path || '');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '重新处理失败');
    } finally {
      setReprocessing(false);
    }
  };

  const getStageLabel = (stageName: string): string => {
    const stage = pipelineState?.stages.find(s => s.stage_name === stageName);
    return stage?.stage_label || stageName;
  };

  const getStageStatusClass = (status: string): string => {
    switch (status) {
      case 'completed': return 'stage-completed';
      case 'failed': return 'stage-failed';
      case 'in_progress': return 'stage-in-progress';
      default: return 'stage-pending';
    }
  };

  const canSelectStage = (stage: StageInfo): boolean => {
    // 第一个阶段总是可以选择
    if (stage.stage_id === 1) return true;
    
    // 检查前置阶段是否都已完成
    const allStages = pipelineState?.stages || [];
    for (const s of allStages) {
      if (s.stage_id < stage.stage_id && s.status !== 'completed') {
        return false;
      }
    }
    return true;
  };

  const formatTime = (timeStr?: string): string => {
    if (!timeStr) return '';
    try {
      return new Date(timeStr).toLocaleTimeString('zh-CN');
    } catch {
      return '';
    }
  };

  return (
    <div className="stage-selector-overlay" onClick={onClose}>
      <div className="stage-selector-modal" onClick={e => e.stopPropagation()}>
        <div className="stage-selector-header">
          <h2>选择重新处理的起始阶段</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="stage-selector-content">
          {loading && <div className="loading">加载中...</div>}
          
          {error && <div className="error-message">{error}</div>}

          {!loading && pipelineState && (
            <>
              <div className="video-info">
                <p><strong>视频:</strong> {pipelineState.video_name}</p>
                <p><strong>更新时间:</strong> {new Date(pipelineState.updated_at).toLocaleString('zh-CN')}</p>
              </div>

              <div className="stages-list">
                <h3>处理阶段</h3>
                {pipelineState.stages.map((stage) => {
                  const selectable = canSelectStage(stage);
                  return (
                    <div
                      key={stage.stage_id}
                      className={`stage-item ${getStageStatusClass(stage.status)} ${
                        selectedStage === stage.stage_name ? 'selected' : ''
                      } ${!selectable ? 'disabled' : ''}`}
                      onClick={() => selectable && setSelectedStage(stage.stage_name)}
                      title={!selectable ? '前置阶段未完成' : ''}
                    >
                      <div className="stage-number">{stage.stage_id}</div>
                      <div className="stage-info">
                        <div className="stage-name">{stage.stage_label}</div>
                        <div className="stage-status">
                          {stage.status === 'completed' && '已完成'}
                          {stage.status === 'failed' && '失败'}
                          {stage.status === 'in_progress' && '处理中'}
                          {stage.status === 'pending' && '待处理'}
                        </div>
                        {stage.completed_at && (
                          <div className="stage-time">
                            {formatTime(stage.completed_at)}
                          </div>
                        )}
                        {stage.error && (
                          <div className="stage-error">{stage.error}</div>
                        )}
                      </div>
                      <input
                        type="radio"
                        name="stage"
                        checked={selectedStage === stage.stage_name}
                        onChange={() => selectable && setSelectedStage(stage.stage_name)}
                        disabled={!selectable}
                      />
                    </div>
                  );
                })}
              </div>

              <div className="hotwords-section">
                <h3>热词设置（可选）</h3>
                <textarea
                  className="hotwords-input"
                  placeholder={'每行一个热词...\n例如：\n机器学习\n深度学习'}
                  value={hotwords}
                  onChange={(e) => setHotwords(e.target.value)}
                  rows={5}
                />
                <p className="hotwords-hint">
                  热词将应用于语音识别及后续阶段
                </p>
              </div>

              <div className="stage-selector-actions">
                <button
                  className="reprocess-btn"
                  onClick={handleReprocess}
                  disabled={!selectedStage || reprocessing}
                >
                  {reprocessing ? '处理中...' : '开始重新处理'}
                </button>
                <button className="cancel-btn" onClick={onClose}>
                  取消
                </button>
              </div>

              <div className="stage-selector-warning">
                <strong>注意:</strong> 从选定阶段开始重新处理将覆盖该阶段及后续所有阶段的结果。
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
