import { useState, useCallback } from 'react';
import { Group, Panel, Separator } from 'react-resizable-panels';
import { VideoPlayer } from './components/VideoPlayer';
import { SubtitlePanel } from './components/SubtitlePanel';
import { LecturePanel } from './components/LecturePanel';
import { ProgressBar } from './components/ProgressBar';
import { ExportButton } from './components/ExportButton';
import { FileUpload } from './components/FileUpload';
import { HotWordsInput } from './components/HotWordsInput';
import { HistoryList } from './components/HistoryList';
import { StageSelector } from './components/StageSelector';
import { useVideoSync } from './hooks/useVideoSync';
import { useWebSocket } from './hooks/useWebSocket';
import { uploadVideo, getTaskResult, loadHistoryResult, startProcessing, checkDuplicate, DuplicateInfo } from './services/api';
import { SubtitleEntry, Section, Lecture, ProcessingStage, HistoryItem } from './types';
import { DuplicateDialog } from './components/DuplicateDialog';
import './App.css';

type AppState = 'idle' | 'uploaded' | 'uploading' | 'processing' | 'completed' | 'error';

function App() {
  // 状态管理
  const [appState, setAppState] = useState<AppState>('idle');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [hotwords, setHotwords] = useState<string>('');
  const [subtitles, setSubtitles] = useState<SubtitleEntry[]>([]);
  const [lecture, setLecture] = useState<Lecture | null>(null);
  const [processingStages, setProcessingStages] = useState<ProcessingStage[]>([]);
  const [progressMessage, setProgressMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [showStageSelector, setShowStageSelector] = useState(false);
  const [reprocessTaskId, setReprocessTaskId] = useState<string | null>(null);
  const [duplicateInfo, setDuplicateInfo] = useState<{ filename: string; duplicates: DuplicateInfo[]; file: File; hotwordsInput: string } | null>(null);

  // 视频同步
  const {
    videoRef,
    currentSubtitle,
    currentSection,
    seekToSubtitle,
    seekToSection,
  } = useVideoSync({
    subtitles,
    sections: lecture?.sections || [],
  });

  // WebSocket进度监听
  useWebSocket((appState === 'processing' || appState === 'uploaded') && taskId ? taskId : null, {
    onMessage: async (message) => {
      setProcessingStages(message.stages);
      setProgressMessage(message.message);

      // 处理完成
      if (message.stage === 'done') {
        try {
          const result = await getTaskResult(taskId!);
          setSubtitles(result.subtitles);
          setLecture(result.lecture);
          // 构建视频URL
          const videoPath = result.video_path;
          // 假设视频在uploads目录下
          const filename = videoPath.split('/').pop();
          setVideoUrl(`/uploads/${filename}`);
          setAppState('completed');
        } catch (error) {
          console.error('获取结果失败:', error);
          setAppState('error');
          setErrorMessage('获取处理结果失败');
        }
      }

      // 处理错误
      if (message.stage === 'error') {
        setAppState('error');
        setErrorMessage(message.message);
      }
    },
  });

  // 执行实际上传
  const doUpload = useCallback(async (file: File, hotwordsInput: string, overwriteTaskId?: string) => {
    setAppState('uploading');
    setErrorMessage('');
    
    try {
      const localUrl = URL.createObjectURL(file);
      setVideoUrl(localUrl);
      setHotwords(hotwordsInput);
      
      const response = await uploadVideo(file, overwriteTaskId);
      setTaskId(response.task_id);
      setAppState('uploaded');
      
      setProgressMessage('视频已上传，请点击"开始处理"按钮开始处理');
    } catch (error) {
      console.error('上传失败:', error);
      setAppState('error');
      setErrorMessage(error instanceof Error ? error.message : '上传失败');
    }
  }, []);

  // 处理文件上传（先检测重复）
  const handleFileSelect = useCallback(async (file: File, hotwordsInput: string) => {
    setErrorMessage('');
    
    try {
      // 检查是否有同名视频
      const result = await checkDuplicate(file.name);
      if (result.has_duplicate) {
        // 显示重复对话框，暂存文件信息
        setDuplicateInfo({ filename: file.name, duplicates: result.duplicates, file, hotwordsInput });
        return;
      }
    } catch {
      // 检查失败不阻断上传
    }
    
    await doUpload(file, hotwordsInput);
  }, [doUpload]);

  // 重复对话框回调
  const handleDuplicateCancel = useCallback(async (openTaskId?: string) => {
    setDuplicateInfo(null);
    if (openTaskId) {
      try {
        const result = await loadHistoryResult(openTaskId);
        setTaskId(openTaskId);
        setSubtitles(result.subtitles);
        setLecture(result.lecture);
        const videoPath = result.video_path;
        const filename = videoPath.split('/').pop();
        setVideoUrl(`/uploads/${filename}`);
        setAppState('completed');
      } catch (error) {
        console.error('加载历史记录失败:', error);
        setAppState('error');
        setErrorMessage(error instanceof Error ? error.message : '加载历史记录失败');
      }
    }
  }, []);

  const handleDuplicateOverwrite = useCallback(async (taskId: string) => {
    if (!duplicateInfo) return;
    setDuplicateInfo(null);
    await doUpload(duplicateInfo.file, duplicateInfo.hotwordsInput, taskId);
  }, [duplicateInfo, doUpload]);

  const handleDuplicateNewUpload = useCallback(async () => {
    if (!duplicateInfo) return;
    setDuplicateInfo(null);
    await doUpload(duplicateInfo.file, duplicateInfo.hotwordsInput);
  }, [duplicateInfo, doUpload]);

  // 处理字幕点击
  const handleSubtitleClick = useCallback((subtitle: SubtitleEntry) => {
    seekToSubtitle(subtitle);
  }, [seekToSubtitle]);

  // 处理小节点击
  const handleSectionClick = useCallback((section: Section) => {
    seekToSection(section);
  }, [seekToSection]);

  // 重新开始
  const handleReset = () => {
    setAppState('idle');
    setTaskId(null);
    setVideoUrl(null);
    setHotwords('');
    setSubtitles([]);
    setLecture(null);
    setProcessingStages([]);
    setProgressMessage('');
    setErrorMessage('');
  };

  // 开始处理视频
  const handleStartProcessing = useCallback(async () => {
    if (!taskId) {
      setErrorMessage('没有待处理的视频');
      return;
    }

    try {
      // 调用后端API开始处理，传入热词
      await startProcessing(taskId, hotwords);
      
      setAppState('processing');
      
      // 初始化处理阶段（与后端保持一致）
      setProcessingStages([
        { name: 'extract_audio', label: '提取音频', status: 'pending', progress: 0 },
        { name: 'asr', label: '语音识别', status: 'pending', progress: 0 },
        { name: 'text_correct', label: '文本纠错', status: 'pending', progress: 0 },
        { name: 'align', label: '时间对齐', status: 'pending', progress: 0 },
        { name: 'subtitle', label: '生成字幕', status: 'pending', progress: 0 },
        { name: 'section_split', label: '划分小节', status: 'pending', progress: 0 },
        { name: 'lecture_gen', label: '生成讲义', status: 'pending', progress: 0 },
      ]);
      setProgressMessage('开始处理视频...');
    } catch (error) {
      console.error('启动处理失败:', error);
      setAppState('error');
      setErrorMessage(error instanceof Error ? error.message : '启动处理失败');
    }
  }, [taskId, hotwords]);

  // 加载历史记录
  const handleHistorySelect = useCallback(async (item: HistoryItem) => {
    setShowHistory(false);
    setErrorMessage('');
    
    try {
      const result = await loadHistoryResult(item.id);
      setTaskId(item.id);
      setSubtitles(result.subtitles);
      setLecture(result.lecture);
      // 构建视频URL
      const videoPath = result.video_path;
      const filename = videoPath.split('/').pop();
      setVideoUrl(`/uploads/${filename}`);
      setAppState('completed');
    } catch (error) {
      console.error('加载历史记录失败:', error);
      setAppState('error');
      setErrorMessage(error instanceof Error ? error.message : '加载历史记录失败');
    }
  }, []);

  // 打开重新处理对话框
  const handleReprocessRequest = useCallback((item: HistoryItem) => {
    setReprocessTaskId(item.id);
    setShowHistory(false);
    setShowStageSelector(true);
  }, []);

  // 开始重新处理
  const handleReprocessStart = useCallback((taskId: string, startStage: string, videoPath: string) => {
    setTaskId(taskId);
    setAppState('processing');
    setShowStageSelector(false);
    
    // 设置视频URL
    if (videoPath) {
      setVideoUrl(`/api/video/stream/${encodeURIComponent(videoPath)}`);
    }
    
    // 定义所有阶段
    const allStages = [
      { name: 'extract_audio', label: '提取音频' },
      { name: 'asr', label: '语音识别' },
      { name: 'text_correct', label: '文本纠错' },
      { name: 'align', label: '时间对齐' },
      { name: 'subtitle', label: '生成字幕' },
      { name: 'section_split', label: '划分小节' },
      { name: 'lecture_gen', label: '生成讲义' },
    ];
    
    // 找到起始阶段的索引
    const startIndex = allStages.findIndex(s => s.name === startStage);
    
    // 根据起始阶段设置状态：起始阶段之前的已完成，起始阶段及之后的pending
    const stages: ProcessingStage[] = allStages.map((stage, index) => ({
      name: stage.name,
      label: stage.label,
      status: index < startIndex ? 'completed' : 'pending',
      progress: index < startIndex ? 100 : 0,
    }));
    
    setProcessingStages(stages);
    setProgressMessage(`从"${allStages[startIndex]?.label || startStage}"阶段开始重新处理...`);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>课程教学视频处理系统</h1>
        {appState === 'completed' && (
          <div className="header-actions">
            <ExportButton
              taskId={taskId!}
              lectureTitle={lecture?.title || '讲义'}
            />
            <button className="reset-btn" onClick={handleReset}>
              处理新视频
            </button>
          </div>
        )}
      </header>

      <main className="app-main">
        {/* 上传状态 */}
        {appState === 'idle' && (
          <div className="upload-section">
            <FileUpload onFileSelect={handleFileSelect} />
            <div className="history-action">
              <button className="history-btn" onClick={() => setShowHistory(true)}>
                查看历史记录
              </button>
            </div>
          </div>
        )}

        {/* 已上传状态 - 显示视频预览、热词输入和处理按钮 */}
        {appState === 'uploaded' && (
          <div className="uploaded-section">
            <div className="preview-area">
              <VideoPlayer ref={videoRef} src={videoUrl} />
            </div>
            <div className="hotwords-section">
              <HotWordsInput
                value={hotwords}
                onChange={setHotwords}
                label="热词列表（可选，提升识别准确率）"
                placeholder="请输入热词，每行一个...&#10;例如：&#10;机器学习&#10;深度学习&#10;神经网络"
              />
            </div>
            <div className="upload-controls">
              <button className="process-btn" onClick={handleStartProcessing}>
                开始处理
              </button>
              <button className="reset-btn" onClick={handleReset}>
                重新选择
              </button>
            </div>
            <div className="progress-message">{progressMessage}</div>
          </div>
        )}

        {/* 处理中状态 */}
        {(appState === 'uploading' || appState === 'processing') && (
          <div className="processing-section">
            <div className="preview-area">
              <VideoPlayer ref={videoRef} src={videoUrl} />
            </div>
            <ProgressBar
              stages={processingStages}
              currentMessage={progressMessage}
            />
          </div>
        )}

        {/* 错误状态 */}
        {appState === 'error' && (
          <div className="error-section">
            <div className="error-message">
              <h2>处理失败</h2>
              <p>{errorMessage}</p>
              <button onClick={handleReset}>重新开始</button>
            </div>
          </div>
        )}

        {/* 完成状态 - 主界面 */}
        {appState === 'completed' && (
          <div className="result-section">
            <Group orientation="horizontal">
              {/* 左侧面板：视频 + 字幕 */}
              <Panel defaultSize={50} minSize={30}>
                <Group orientation="vertical">
                  {/* 视频区域 */}
                  <Panel defaultSize={60} minSize={30}>
                    <div className="video-area">
                      <VideoPlayer ref={videoRef} src={videoUrl} />
                    </div>
                  </Panel>
                  <Separator className="resize-handle-horizontal" />
                  {/* 字幕区域 */}
                  <Panel minSize={20}>
                    <div className="subtitle-area">
                      <SubtitlePanel
                        subtitles={subtitles}
                        currentSubtitle={currentSubtitle}
                        onSubtitleClick={handleSubtitleClick}
                      />
                    </div>
                  </Panel>
                </Group>
              </Panel>
              
              <Separator className="resize-handle-vertical" />
              
              {/* 右侧讲义面板 */}
              <Panel defaultSize={50} minSize={25}>
                <div className="lecture-area">
                  <LecturePanel
                    sections={lecture?.sections || []}
                    currentSection={currentSection}
                    onSectionClick={handleSectionClick}
                  />
                </div>
              </Panel>
            </Group>
          </div>
        )}
      </main>

      <footer className="app-footer">
        <p>课程教学视频处理系统 v1.0</p>
      </footer>

      {/* 历史记录弹窗 */}
      {showHistory && (
        <HistoryList
          onSelect={handleHistorySelect}
          onReprocess={handleReprocessRequest}
          onClose={() => setShowHistory(false)}
        />
      )}

      {/* 阶段选择器弹窗 */}
      {showStageSelector && reprocessTaskId && (
        <StageSelector
          taskId={reprocessTaskId}
          onReprocess={handleReprocessStart}
          onClose={() => {
            setShowStageSelector(false);
            setReprocessTaskId(null);
          }}
        />
      )}

      {/* 同名视频检测对话框 */}
      {duplicateInfo && (
        <DuplicateDialog
          filename={duplicateInfo.filename}
          duplicates={duplicateInfo.duplicates}
          onCancel={handleDuplicateCancel}
          onOverwrite={handleDuplicateOverwrite}
          onNewUpload={handleDuplicateNewUpload}
        />
      )}
    </div>
  );
}

export default App;
