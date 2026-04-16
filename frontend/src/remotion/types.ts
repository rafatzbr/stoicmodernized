export type RemotionScene = {
  sceneNumber: number;
  imageSrc: string;
  startTime: number;
  endTime: number;
  narrationSegment: string;
  textOverlay?: string | null;
  animationStyle?: string | null;
};

export type RemotionSubtitle = {
  startTime: number;
  endTime: number;
  text: string;
  words?: {startTime: number; endTime: number; text: string}[] | null;
};

export type RemotionPlatform = 'youtube' | 'tiktok';

export type RemotionRenderProps = {
  title: string;
  topic: string;
  channelName: string;
  mode: 'landscape' | 'portrait';
  platform?: RemotionPlatform;
  fps: number;
  durationInSeconds: number;
  audioSrc: string;
  logoSrc?: string | null;
  scenes: RemotionScene[];
  subtitles: RemotionSubtitle[];
  ctaText?: string | null;
};
