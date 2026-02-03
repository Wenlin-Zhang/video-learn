import React, { forwardRef } from 'react';

interface VideoPlayerProps {
  src: string | null;
  onTimeUpdate?: (time: number) => void;
}

export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  ({ src, onTimeUpdate }, ref) => {
    const handleTimeUpdate = (e: React.SyntheticEvent<HTMLVideoElement>) => {
      onTimeUpdate?.(e.currentTarget.currentTime);
    };

    if (!src) {
      return (
        <div className="video-placeholder">
          <p>请上传视频文件</p>
        </div>
      );
    }

    return (
      <div className="video-container">
        <video
          ref={ref}
          src={src}
          controls
          onTimeUpdate={handleTimeUpdate}
          className="video-player"
        >
          您的浏览器不支持视频播放
        </video>
      </div>
    );
  }
);

VideoPlayer.displayName = 'VideoPlayer';
