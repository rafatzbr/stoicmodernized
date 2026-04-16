import React, {useMemo} from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  staticFile,
  interpolate,
  spring,
  useCurrentFrame,
} from 'remotion';
import type {RemotionRenderProps, RemotionScene} from './types';

const TEXT_COLOR = '#ffffff';
const HIGHLIGHT_COLOR = '#FFD166';
const BRAND_ACCENT = '#F59E0B';
const BRAND_ACCENT_2 = '#FB7185';

const resolveAssetSrc = (src: string) => {
  return /^https?:\/\//.test(src) ? src : staticFile(src);
};

const getSceneTransform = (
  scene: RemotionScene,
  localFrame: number,
  durationInFrames: number,
) => {
  const progress = durationInFrames <= 1 ? 1 : localFrame / Math.max(1, durationInFrames - 1);

  switch (scene.animationStyle) {
    case 'pan-left':
      return `scale(1.08) translateX(${interpolate(progress, [0, 1], [2, -2])}%)`;
    case 'pan-right':
      return `scale(1.08) translateX(${interpolate(progress, [0, 1], [-2, 2])}%)`;
    case 'fade':
      return `scale(${interpolate(progress, [0, 1], [1.02, 1.06])})`;
    case 'zoom':
    default:
      return `scale(${interpolate(progress, [0, 1], [1.04, 1.12])})`;
  }
};

const StoicVideo: React.FC<RemotionRenderProps> = ({
  title,
  topic,
  channelName,
  mode,
  fps,
  scenes,
  subtitles,
  durationInSeconds,
  audioSrc,
  logoSrc,
  ctaText,
}) => {
  const frame = useCurrentFrame();
  const isPortrait = mode === 'portrait';
  const totalFrames = Math.max(1, Math.round(durationInSeconds * fps));

  const subtitleCardStyle: React.CSSProperties = useMemo(() => ({
    position: 'absolute',
    left: isPortrait ? '6%' : '8%',
    right: isPortrait ? '6%' : '8%',
    bottom: isPortrait ? 120 : 62,
    zIndex: 30,
    padding: isPortrait ? '20px 22px 24px' : '18px 26px 22px',
    borderRadius: isPortrait ? 28 : 22,
    background: 'linear-gradient(180deg, rgba(6,8,16,0.34), rgba(6,8,16,0.78))',
    border: '1px solid rgba(255,255,255,0.1)',
    boxShadow: '0 22px 80px rgba(0,0,0,0.45)',
    backdropFilter: 'blur(18px)',
  }), [isPortrait]);

  const channelStyle: React.CSSProperties = {
    position: 'absolute',
    top: isPortrait ? 82 : 48,
    left: isPortrait ? 34 : 54,
    zIndex: 25,
    padding: isPortrait ? '10px 16px' : '10px 18px',
    borderRadius: 999,
    background: 'rgba(7,10,20,0.45)',
    border: '1px solid rgba(255,255,255,0.12)',
    fontSize: isPortrait ? 24 : 28,
    fontWeight: 700,
    letterSpacing: '0.04em',
    color: TEXT_COLOR,
    textTransform: 'uppercase',
    boxShadow: '0 10px 30px rgba(0,0,0,0.28)',
  };

  const titleStyle: React.CSSProperties = {
    position: 'absolute',
    top: isPortrait ? 148 : 104,
    left: isPortrait ? 34 : 54,
    right: isPortrait ? 34 : 54,
    zIndex: 25,
    fontSize: isPortrait ? 50 : 54,
    lineHeight: 1.03,
    fontWeight: 900,
    letterSpacing: '-0.03em',
    color: TEXT_COLOR,
    textShadow: '0 8px 28px rgba(0,0,0,0.45)',
    maxWidth: isPortrait ? '85%' : '62%',
  };

  const progressStyle: React.CSSProperties = {
    position: 'absolute',
    top: isPortrait ? 48 : 32,
    left: isPortrait ? '6%' : '18%',
    width: isPortrait ? '88%' : '64%',
    height: isPortrait ? 8 : 6,
    borderRadius: 999,
    overflow: 'hidden',
    background: 'rgba(255,255,255,0.15)',
    zIndex: 35,
  };

  const progressFillStyle: React.CSSProperties = {
    width: `${Math.min(100, (frame / totalFrames) * 100)}%`,
    height: '100%',
    background: `linear-gradient(90deg, ${BRAND_ACCENT_2}, ${BRAND_ACCENT}, ${HIGHLIGHT_COLOR})`,
    boxShadow: `0 0 24px ${BRAND_ACCENT}`,
    borderRadius: 999,
  };

  const logoStyle: React.CSSProperties = {
    position: 'absolute',
    top: isPortrait ? 42 : 28,
    right: isPortrait ? 26 : 34,
    width: isPortrait ? 76 : 110,
    height: 'auto',
    zIndex: 30,
    opacity: 0.88,
    filter: 'drop-shadow(0 8px 20px rgba(0,0,0,0.35))',
  };

  const vignetteStyle: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    background: [
      'radial-gradient(circle at center, transparent 30%, rgba(0,0,0,0.36) 100%)',
      'linear-gradient(180deg, rgba(4,8,18,0.58) 0%, rgba(4,8,18,0.08) 22%, rgba(4,8,18,0.1) 68%, rgba(4,8,18,0.8) 100%)',
    ].join(','),
    zIndex: 5,
  };

  const ctaPulse = spring({
    fps,
    frame: Math.max(0, frame - Math.max(0, totalFrames - Math.round(2.4 * fps))),
    config: {damping: 200, stiffness: 120},
  });

  return (
    <AbsoluteFill style={{backgroundColor: '#050816'}}>
      <Audio src={resolveAssetSrc(audioSrc)} volume={0.9} />

      {scenes.map((scene) => {
        const from = Math.round(scene.startTime * fps);
        const durationInFrames = Math.max(1, Math.round((scene.endTime - scene.startTime) * fps));

        return (
          <Sequence key={scene.sceneNumber} from={from} durationInFrames={durationInFrames}>
            <SceneLayer
              scene={scene}
              durationInFrames={durationInFrames}
              isPortrait={isPortrait}
              fps={fps}
            />
          </Sequence>
        );
      })}

      <AbsoluteFill style={vignetteStyle} />

      <div style={progressStyle}>
        <div style={progressFillStyle} />
      </div>

      <div style={channelStyle}>{channelName}</div>
      <div style={titleStyle}>{topic || title}</div>

      {logoSrc ? <Img src={resolveAssetSrc(logoSrc)} style={logoStyle} /> : null}

      {subtitles.map((sub, idx) => {
        const startFrame = Math.round(sub.startTime * fps);
        const endFrame = Math.round(sub.endTime * fps);
        const isActive = frame >= startFrame && frame < endFrame;

        if (!isActive) {
          return null;
        }

        const localFrame = frame - startFrame;
        const subtitleIn = spring({
          fps,
          frame: localFrame,
          config: {damping: 200, stiffness: 180},
        });

        const words = sub.words?.length
          ? sub.words
          : sub.text.split(' ').map((word, wordIndex, arr) => {
              const start = sub.startTime + ((sub.endTime - sub.startTime) * wordIndex) / arr.length;
              const end = sub.startTime + ((sub.endTime - sub.startTime) * (wordIndex + 1)) / arr.length;
              return {startTime: start, endTime: end, text: word};
            });

        const activeWordIndex = words.findIndex((word, wordIndex) => {
          const wordStart = Math.round(word.startTime * fps);
          const nextStart =
            wordIndex === words.length - 1 ? endFrame : Math.round(words[wordIndex + 1].startTime * fps);
          return frame >= wordStart && frame < nextStart;
        });

        return (
          <div
            key={idx}
            style={{
              ...subtitleCardStyle,
              transform: `translateY(${interpolate(subtitleIn, [0, 1], [22, 0])}px) scale(${interpolate(
                subtitleIn,
                [0, 1],
                [0.97, 1],
              )})`,
              opacity: subtitleIn,
            }}
          >
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                justifyContent: 'center',
                gap: isPortrait ? '8px 10px' : '10px 12px',
                fontSize: isPortrait ? 54 : 62,
                lineHeight: 1.08,
                fontWeight: 900,
                letterSpacing: '-0.03em',
                textAlign: 'center',
                color: TEXT_COLOR,
                textShadow: '0 6px 26px rgba(0,0,0,0.4)',
              }}
            >
              {words.map((word, wordIndex) => {
                const isActiveWord = wordIndex === activeWordIndex;
                return (
                  <span
                    key={`${idx}-${wordIndex}`}
                    style={{
                      color: isActiveWord ? '#111827' : TEXT_COLOR,
                      background: isActiveWord
                        ? `linear-gradient(135deg, ${HIGHLIGHT_COLOR}, ${BRAND_ACCENT})`
                        : 'transparent',
                      padding: isActiveWord ? '0.08em 0.18em' : 0,
                      borderRadius: isActiveWord ? 14 : 0,
                      boxShadow: isActiveWord ? '0 10px 30px rgba(245,158,11,0.35)' : 'none',
                      transform: isActiveWord ? 'scale(1.04)' : 'scale(1)',
                      transition: 'all 120ms ease-out',
                    }}
                  >
                    {word.text}
                  </span>
                );
              })}
            </div>
          </div>
        );
      })}

      {ctaText ? (
        <Sequence
          from={Math.max(0, totalFrames - Math.round(3 * fps))}
          durationInFrames={Math.round(3 * fps)}
        >
          <AbsoluteFill
            style={{
              justifyContent: 'center',
              alignItems: 'center',
              padding: isPortrait ? '64px' : '80px',
              background: 'linear-gradient(135deg, rgba(5,8,22,0.9), rgba(17,24,39,0.88), rgba(88,28,135,0.82))',
              zIndex: 40,
            }}
          >
            <div
              style={{
                padding: isPortrait ? '18px 22px' : '16px 22px',
                borderRadius: 999,
                border: '1px solid rgba(255,255,255,0.14)',
                background: 'rgba(255,255,255,0.06)',
                color: HIGHLIGHT_COLOR,
                textTransform: 'uppercase',
                letterSpacing: '0.18em',
                fontWeight: 800,
                marginBottom: isPortrait ? 22 : 16,
                transform: `scale(${interpolate(ctaPulse, [0, 1], [0.92, 1])})`,
              }}
            >
              Stoic Modernized
            </div>
            <div
              style={{
                color: TEXT_COLOR,
                fontSize: isPortrait ? 84 : 92,
                fontWeight: 950,
                lineHeight: 0.95,
                letterSpacing: '-0.05em',
                textAlign: 'center',
                marginBottom: isPortrait ? 24 : 18,
                textShadow: '0 12px 40px rgba(0,0,0,0.35)',
                transform: `translateY(${interpolate(ctaPulse, [0, 1], [24, 0])}px)`,
              }}
            >
              Subscribe for
              <br />
              calm ambition
            </div>
            <div
              style={{
                maxWidth: isPortrait ? '88%' : '70%',
                textAlign: 'center',
                color: 'rgba(255,255,255,0.92)',
                fontSize: isPortrait ? 32 : 34,
                lineHeight: 1.2,
                fontWeight: 600,
              }}
            >
              {ctaText}
            </div>
          </AbsoluteFill>
        </Sequence>
      ) : null}

      {!isPortrait ? (
        <div
          style={{
            position: 'absolute',
            right: 54,
            bottom: 54,
            zIndex: 25,
            padding: '14px 18px',
            borderRadius: 18,
            background: 'rgba(7,10,20,0.45)',
            border: '1px solid rgba(255,255,255,0.08)',
            color: 'rgba(255,255,255,0.9)',
            fontSize: 24,
            fontWeight: 700,
            letterSpacing: '0.02em',
          }}
        >
          Practical Stoicism for modern work
        </div>
      ) : null}

      {isPortrait ? (
        <div
          style={{
            position: 'absolute',
            right: 26,
            top: 110,
            zIndex: 30,
            writingMode: 'vertical-rl',
            textOrientation: 'mixed',
            color: 'rgba(255,255,255,0.55)',
            fontSize: 18,
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            fontWeight: 700,
          }}
        >
          Stoic Modernized
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const SceneLayer: React.FC<{
  scene: RemotionScene;
  durationInFrames: number;
  isPortrait: boolean;
  fps: number;
}> = ({scene, durationInFrames, isPortrait, fps}) => {
  const frame = useCurrentFrame();
  const entrance = spring({
    fps,
    frame,
    config: {damping: 200, stiffness: 140},
  });
  const transform = getSceneTransform(scene, frame, durationInFrames);
  const overlayY = interpolate(entrance, [0, 1], [16, 0]);

  return (
    <AbsoluteFill>
      <Img
        src={resolveAssetSrc(scene.imageSrc)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform,
        }}
      />
      <AbsoluteFill
        style={{
          background: isPortrait
            ? 'linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.18))'
            : 'linear-gradient(180deg, rgba(0,0,0,0.08), rgba(0,0,0,0.14))',
        }}
      />
      {scene.textOverlay ? (
        <div
          style={{
            position: 'absolute',
            top: isPortrait ? 230 : 180,
            left: isPortrait ? 34 : 54,
            zIndex: 12,
            padding: isPortrait ? '14px 20px' : '14px 22px',
            borderRadius: 18,
            background: 'linear-gradient(135deg, rgba(17,24,39,0.62), rgba(88,28,135,0.42))',
            border: '1px solid rgba(255,255,255,0.12)',
            color: TEXT_COLOR,
            fontSize: isPortrait ? 28 : 30,
            fontWeight: 800,
            letterSpacing: '0.02em',
            transform: `translateY(${overlayY}px)`,
            opacity: entrance,
            boxShadow: '0 18px 40px rgba(0,0,0,0.25)',
          }}
        >
          {scene.textOverlay}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export {StoicVideo};
