import type {RemotionRenderProps} from './types';

const baseScenes = [
  {
    sceneNumber: 1,
    imageSrc: 'https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1200&q=80',
    startTime: 0,
    endTime: 5.5,
    narrationSegment: 'Your job is demanding more than your time, it is stealing your peace.',
    textOverlay: 'Protect Your Peace',
    animationStyle: 'zoom',
  },
  {
    sceneNumber: 2,
    imageSrc: 'https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1200&q=80',
    startTime: 5.5,
    endTime: 11.5,
    narrationSegment: 'The Stoic move is to separate what is yours to control from what is not.',
    textOverlay: 'Dichotomy of Control',
    animationStyle: 'pan-left',
  },
  {
    sceneNumber: 3,
    imageSrc: 'https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?auto=format&fit=crop&w=1200&q=80',
    startTime: 11.5,
    endTime: 17.0,
    narrationSegment: 'Calm boundaries make you look more competent, not less committed.',
    textOverlay: 'Calm > Panic',
    animationStyle: 'pan-right',
  },
];

const baseSubtitles = [
  {startTime: 0, endTime: 3.2, text: 'Your job is demanding more than your time.'},
  {startTime: 3.2, endTime: 7.2, text: 'It is stealing your peace.'},
  {startTime: 7.2, endTime: 12.0, text: 'Separate what you control from what you do not.'},
  {startTime: 12.0, endTime: 17.0, text: 'Calm boundaries make you look more competent.'},
];

export const sampleLandscapeProps: RemotionRenderProps = {
  title: 'Set Work Boundaries Without Getting Fired',
  topic: 'Set Work Boundaries Without Getting Fired',
  channelName: 'Stoic Modernized',
  mode: 'landscape',
  platform: 'youtube',
  fps: 30,
  durationInSeconds: 17,
  audioSrc: 'https://cdn.pixabay.com/download/audio/2022/03/10/audio_c8b0f73443.mp3?filename=inspiring-cinematic-ambient-116199.mp3',
  backgroundMusicSrc: 'https://cdn.pixabay.com/download/audio/2022/03/15/audio_c9d3f12f1f.mp3?filename=meditation-relaxing-ambient-114126.mp3',
  backgroundMusicVolume: 0.12,
  scenes: baseScenes,
  subtitles: baseSubtitles,
  ctaText: 'Subscribe for more practical Stoicism',
};

export const samplePortraitProps: RemotionRenderProps = {
  ...sampleLandscapeProps,
  mode: 'portrait',
  platform: 'tiktok',
};
