import React from 'react';
import {Composition} from 'remotion';
import {StoicVideo} from './StoicVideo';
import {sampleLandscapeProps, samplePortraitProps} from './sample-props';
import type {RemotionRenderProps} from './types';

const getDurationInFrames = (props: RemotionRenderProps) => {
  return Math.max(1, Math.round(props.durationInSeconds * props.fps));
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="StoicLandscape"
        component={StoicVideo}
        durationInFrames={getDurationInFrames(sampleLandscapeProps)}
        fps={sampleLandscapeProps.fps}
        width={1920}
        height={1080}
        defaultProps={sampleLandscapeProps}
        calculateMetadata={({props}) => ({
          durationInFrames: getDurationInFrames(props as RemotionRenderProps),
          fps: (props as RemotionRenderProps).fps,
          width: 1920,
          height: 1080,
        })}
      />
      <Composition
        id="StoicPortrait"
        component={StoicVideo}
        durationInFrames={getDurationInFrames(samplePortraitProps)}
        fps={samplePortraitProps.fps}
        width={1080}
        height={1920}
        defaultProps={samplePortraitProps}
        calculateMetadata={({props}) => ({
          durationInFrames: getDurationInFrames(props as RemotionRenderProps),
          fps: (props as RemotionRenderProps).fps,
          width: 1080,
          height: 1920,
        })}
      />
    </>
  );
};
