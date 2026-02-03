import { useState, useCallback, useRef, useEffect } from 'react';
import { SubtitleEntry, Section } from '../types';

interface UseVideoSyncOptions {
  subtitles: SubtitleEntry[];
  sections: Section[];
  onSubtitleChange?: (subtitle: SubtitleEntry | null) => void;
  onSectionChange?: (section: Section | null) => void;
}

export function useVideoSync(options: UseVideoSyncOptions) {
  const { subtitles, sections, onSubtitleChange, onSectionChange } = options;

  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [currentSubtitle, setCurrentSubtitle] = useState<SubtitleEntry | null>(null);
  const [currentSection, setCurrentSection] = useState<Section | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  // 根据时间找到当前字幕
  const findSubtitleAtTime = useCallback((time: number): SubtitleEntry | null => {
    for (const subtitle of subtitles) {
      if (time >= subtitle.start_time && time <= subtitle.end_time) {
        return subtitle;
      }
    }
    // 找最近的已过字幕
    for (let i = subtitles.length - 1; i >= 0; i--) {
      if (time >= subtitles[i].start_time) {
        return subtitles[i];
      }
    }
    return subtitles[0] || null;
  }, [subtitles]);

  // 根据时间找到当前小节
  const findSectionAtTime = useCallback((time: number): Section | null => {
    for (const section of sections) {
      if (time >= section.start_time && time <= section.end_time) {
        return section;
      }
    }
    // 找最近的已过小节
    for (let i = sections.length - 1; i >= 0; i--) {
      if (time >= sections[i].start_time) {
        return sections[i];
      }
    }
    return sections[0] || null;
  }, [sections]);

  // 处理视频时间更新
  const handleTimeUpdate = useCallback(() => {
    if (!videoRef.current) return;

    const time = videoRef.current.currentTime;
    setCurrentTime(time);

    const newSubtitle = findSubtitleAtTime(time);
    if (newSubtitle?.index !== currentSubtitle?.index) {
      setCurrentSubtitle(newSubtitle);
      onSubtitleChange?.(newSubtitle);
    }

    const newSection = findSectionAtTime(time);
    if (newSection?.id !== currentSection?.id) {
      setCurrentSection(newSection);
      onSectionChange?.(newSection);
    }
  }, [findSubtitleAtTime, findSectionAtTime, currentSubtitle, currentSection, onSubtitleChange, onSectionChange]);

  // 跳转到指定时间
  const seekTo = useCallback((time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
    }
  }, []);

  // 跳转到指定字幕
  const seekToSubtitle = useCallback((subtitle: SubtitleEntry) => {
    seekTo(subtitle.start_time);
  }, [seekTo]);

  // 跳转到指定小节
  const seekToSection = useCallback((section: Section) => {
    seekTo(section.start_time);
  }, [seekTo]);

  // 播放/暂停
  const togglePlay = useCallback(() => {
    if (!videoRef.current) return;

    if (videoRef.current.paused) {
      videoRef.current.play();
    } else {
      videoRef.current.pause();
    }
  }, []);

  // 监听播放状态
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);

    video.addEventListener('play', handlePlay);
    video.addEventListener('pause', handlePause);
    video.addEventListener('timeupdate', handleTimeUpdate);

    return () => {
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('timeupdate', handleTimeUpdate);
    };
  }, [handleTimeUpdate]);

  return {
    videoRef,
    currentTime,
    currentSubtitle,
    currentSection,
    isPlaying,
    seekTo,
    seekToSubtitle,
    seekToSection,
    togglePlay,
  };
}
