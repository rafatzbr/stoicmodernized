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
import type {RemotionRenderProps, RemotionScene, RemotionSubtitle} from './types';

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
      return `translateX(${interpolate(progress, [0, 1], [4, -4])}%) translateY(${interpolate(progress, [0, 1], [1.5, -1.5])}%) scale(${interpolate(progress, [0, 1], [1.14, 1.22])})`;
    case 'pan-right':
      return `translateX(${interpolate(progress, [0, 1], [-4, 4])}%) translateY(${interpolate(progress, [0, 1], [-1.5, 1.5])}%) scale(${interpolate(progress, [0, 1], [1.14, 1.22])})`;
    case 'fade':
      return `translateY(${interpolate(progress, [0, 1], [3, -3])}%) scale(${interpolate(progress, [0, 1], [1.12, 1.2])})`;
    case 'zoom':
    default:
      return `translateY(${interpolate(progress, [0, 1], [2.5, -2.5])}%) scale(${interpolate(progress, [0, 1], [1.16, 1.28])})`;
  }
};

type TimedWord = {
  startTime: number;
  endTime: number;
  text: string;
};

type CaptionChunk = {
  startTime: number;
  endTime: number;
  words: TimedWord[];
  text: string;
  hasWordTimings: boolean;
};

const normalizeSubtitleWords = (subtitle: RemotionSubtitle) => {
  if (subtitle.words?.length) {
    return {
      words: subtitle.words.map((word) => ({
        startTime: word.startTime,
        endTime: word.endTime,
        text: word.text,
      })),
      hasWordTimings: true,
    };
  }

  return {
    words: subtitle.text.split(/\s+/).filter(Boolean).map((word) => ({
      startTime: subtitle.startTime,
      endTime: subtitle.endTime,
      text: word,
    })),
    hasWordTimings: false,
  };
};

const chunkWordsForCaptions = (
  words: TimedWord[],
  isPortrait: boolean,
  hasWordTimings: boolean,
): CaptionChunk[] => {
  if (words.length === 0) {
    return [];
  }

  if (!hasWordTimings) {
    return [
      {
        startTime: words[0].startTime,
        endTime: words[0].endTime,
        words: [...words],
        text: words.map((word) => word.text).join(' '),
        hasWordTimings: false,
      },
    ];
  }

  const maxWordsPerChunk = isPortrait ? 4 : 7;
  const chunks: CaptionChunk[] = [];
  let currentChunk: TimedWord[] = [];

  const flushChunk = () => {
    if (currentChunk.length === 0) {
      return;
    }

    chunks.push({
      startTime: currentChunk[0].startTime,
      endTime: currentChunk[currentChunk.length - 1].endTime,
      words: [...currentChunk],
      text: currentChunk.map((word) => word.text).join(' '),
      hasWordTimings: true,
    });
    currentChunk = [];
  };

  for (const word of words) {
    const lastWord = currentChunk[currentChunk.length - 1];
    const pauseBeforeWord = lastWord ? word.startTime - lastWord.endTime : 0;
    const punctuationBreak = /[.!?,:;]$/.test(lastWord?.text ?? '');

    if (
      currentChunk.length >= maxWordsPerChunk ||
      (currentChunk.length >= 2 && pauseBeforeWord >= (isPortrait ? 0.22 : 0.3)) ||
      (currentChunk.length >= 3 && punctuationBreak)
    ) {
      flushChunk();
    }

    currentChunk.push(word);
  }

  flushChunk();
  return chunks;
};

const buildCaptionChunks = (subtitles: RemotionSubtitle[], isPortrait: boolean): CaptionChunk[] => {
  return subtitles.flatMap((subtitle) => {
    const normalized = normalizeSubtitleWords(subtitle);
    return chunkWordsForCaptions(normalized.words, isPortrait, normalized.hasWordTimings);
  });
};

const StoicVideo: React.FC<RemotionRenderProps> = ({
  title,
  topic,
  channelName,
  channelDescription,
  mode,
  fps,
  scenes,
  subtitles,
  durationInSeconds,
  audioSrc,
  backgroundMusicSrc,
  backgroundMusicVolume,
  logoSrc,
  ctaText,
}) => {
  const frame = useCurrentFrame();
  const isPortrait = mode === 'portrait';
  const totalFrames = Math.max(1, Math.round(durationInSeconds * fps));
  const captionChunks = useMemo(() => buildCaptionChunks(subtitles, isPortrait), [subtitles, isPortrait]);
  const normalizedChannelName = channelName.trim().toLowerCase();
  const normalizedTopic = (topic || '').trim();
  const normalizedTitle = (title || '').trim();
  const headerTitle =
    (normalizedTitle && normalizedTitle.toLowerCase() !== normalizedChannelName
      ? normalizedTitle
      : '') ||
    normalizedTopic ||
    channelDescription ||
    'Ancient logic for the high-performance digital age';

  // Find which scene is currently active
  const activeScene = useMemo(() => {
    for (const scene of scenes) {
      const from = Math.round(scene.startTime * fps);
      const to = from + Math.max(1, Math.round((scene.endTime - scene.startTime) * fps));
      if (frame >= from && frame < to) {
        return scene;
      }
    }
    return scenes[0] || null;
  }, [scenes, fps, frame]);

  const kickerText = activeScene?.textOverlay || '';

  const subtitleCardStyle: React.CSSProperties = useMemo(
    () => ({
      position: 'absolute',
      left: isPortrait ? '10%' : '18%',
      right: isPortrait ? '10%' : '18%',
      top: isPortrait ? '50%' : '58%',
      transform: 'translateY(-50%)',
      zIndex: 30,
      padding: isPortrait ? '24px 24px 28px' : '18px 24px 20px',
      borderRadius: isPortrait ? 30 : 18,
      background: isPortrait
        ? 'linear-gradient(180deg, rgba(13,13,25,0.24), rgba(13,13,25,0.76))'
        : 'linear-gradient(180deg, rgba(4,10,20,0.2), rgba(4,10,20,0.58))',
      border: isPortrait ? '1px solid rgba(255,255,255,0.1)' : '1px solid rgba(255,255,255,0.08)',
      boxShadow: isPortrait ? '0 24px 90px rgba(0,0,0,0.48)' : '0 16px 50px rgba(0,0,0,0.32)',
      backdropFilter: 'blur(18px)',
    }),
    [isPortrait],
  );

  const headerStackStyle: React.CSSProperties = {
    position: 'absolute',
    top: isPortrait ? 152 : 42,
    left: isPortrait ? 72 : 54,
    right: isPortrait ? 220 : 180,
    zIndex: 25,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: isPortrait ? 18 : 14,
  };

  const channelStyle: React.CSSProperties = {
    padding: isPortrait ? '10px 15px' : '10px 18px',
    borderRadius: isPortrait ? 18 : 999,
    background: isPortrait ? 'rgba(7,10,20,0.48)' : 'rgba(7,10,20,0.38)',
    border: '1px solid rgba(255,255,255,0.12)',
    fontSize: isPortrait ? 22 : 26,
    fontWeight: 800,
    letterSpacing: isPortrait ? '0.08em' : '0.04em',
    color: TEXT_COLOR,
    textTransform: 'uppercase',
    boxShadow: '0 10px 30px rgba(0,0,0,0.28)',
  };

  const titleStyle: React.CSSProperties = {
    fontSize: isPortrait ? 58 : 48,
    lineHeight: isPortrait ? 0.98 : 1.02,
    fontWeight: 950,
    letterSpacing: '-0.05em',
    color: TEXT_COLOR,
    textShadow: '0 8px 28px rgba(0,0,0,0.45)',
    maxWidth: isPortrait ? '86%' : '58%',
  };

  const kickerStyle: React.CSSProperties = {
    padding: isPortrait ? '12px 16px' : '10px 14px',
    borderRadius: 999,
    background: isPortrait
      ? 'linear-gradient(135deg, rgba(251,113,133,0.85), rgba(245,158,11,0.92))'
      : 'rgba(255,255,255,0.12)',
    color: isPortrait ? '#111827' : 'rgba(255,255,255,0.92)',
    fontSize: isPortrait ? 22 : 20,
    fontWeight: 900,
    letterSpacing: isPortrait ? '0.01em' : '0.01em',
  };

  const progressStyle: React.CSSProperties = {
    position: 'absolute',
    top: isPortrait ? 112 : 30,
    left: isPortrait ? '20%' : '18%',
    width: isPortrait ? '58%' : '64%',
    height: isPortrait ? 8 : 5,
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
    top: isPortrait ? 72 : 28,
    right: isPortrait ? 54 : 34,
    width: 108,
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
      isPortrait
        ? 'linear-gradient(180deg, rgba(4,8,18,0.6) 0%, rgba(4,8,18,0.1) 22%, rgba(4,8,18,0.12) 68%, rgba(4,8,18,0.86) 100%)'
        : 'linear-gradient(180deg, rgba(4,8,18,0.42) 0%, rgba(4,8,18,0.04) 20%, rgba(4,8,18,0.08) 66%, rgba(4,8,18,0.74) 100%)',
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
      {backgroundMusicSrc ? (
        <Audio
          src={resolveAssetSrc(backgroundMusicSrc)}
          volume={backgroundMusicVolume ?? 0.12}
          loop
        />
      ) : null}
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

      <div style={headerStackStyle}>
        <div style={channelStyle}>{channelName}</div>
        <div style={titleStyle}>{headerTitle}</div>
        <div style={kickerStyle}>{kickerText || 'Practical Stoicism for modern work'}</div>
      </div>

      {logoSrc ? <Img src={resolveAssetSrc(logoSrc)} style={logoStyle} /> : null}

      {captionChunks.map((chunk, idx) => {
        const startFrame = Math.round(chunk.startTime * fps);
        const endFrame = Math.round(chunk.endTime * fps);
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
                color: TEXT_COLOR,
                textShadow: '0 6px 26px rgba(0,0,0,0.4)',
                fontSize: isPortrait ? 58 : 46,
                lineHeight: isPortrait ? 1.12 : 1.08,
                fontWeight: 950,
                letterSpacing: '-0.04em',
                textAlign: 'center',
                whiteSpace: 'normal',
                wordBreak: 'normal',
                overflowWrap: 'normal',
                maxWidth: '100%',
              }}
            >
              {chunk.text}
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
              background: isPortrait
                ? 'linear-gradient(135deg, rgba(5,8,22,0.9), rgba(17,24,39,0.88), rgba(88,28,135,0.82))'
                : 'linear-gradient(135deg, rgba(5,8,22,0.94), rgba(10,24,40,0.92), rgba(18,58,92,0.84))',
              zIndex: 40,
            }}
          >
            <div
              style={{
                padding: isPortrait ? '18px 22px' : '14px 20px',
                borderRadius: 999,
                border: '1px solid rgba(255,255,255,0.14)',
                background: 'rgba(255,255,255,0.06)',
                color: HIGHLIGHT_COLOR,
                textTransform: 'uppercase',
                letterSpacing: isPortrait ? '0.18em' : '0.12em',
                fontWeight: 800,
                marginBottom: isPortrait ? 22 : 18,
                transform: `scale(${interpolate(ctaPulse, [0, 1], [0.92, 1])})`,
              }}
            >
              {isPortrait ? channelName : 'Stoic Modernized on YouTube'}
            </div>
            <div
              style={{
                color: TEXT_COLOR,
                fontSize: isPortrait ? 84 : 72,
                fontWeight: 950,
                lineHeight: 0.95,
                letterSpacing: '-0.05em',
                textAlign: 'center',
                marginBottom: isPortrait ? 24 : 18,
                textShadow: '0 12px 40px rgba(0,0,0,0.35)',
                transform: `translateY(${interpolate(ctaPulse, [0, 1], [24, 0])}px)`,
              }}
            >
              <>
                subscribe to
                <br />
                @stoic-modernized
              </>
            </div>
            {ctaText && ctaText.toLowerCase() !== 'subscribe to @stoic-modernized' ? (
              <div
                style={{
                  maxWidth: isPortrait ? '88%' : '62%',
                  textAlign: 'center',
                  color: 'rgba(255,255,255,0.92)',
                  fontSize: isPortrait ? 32 : 28,
                  lineHeight: 1.2,
                  fontWeight: 600,
                }}
              >
                {ctaText}
              </div>
            ) : null}
          </AbsoluteFill>
        </Sequence>
      ) : null}

      {isPortrait ? (
        <div
          style={{
            position: 'absolute',
            right: 72,
            bottom: 120,
            zIndex: 25,
            padding: '14px 18px',
            borderRadius: 18,
            background: 'rgba(7,10,20,0.45)',
            border: '1px solid rgba(255,255,255,0.08)',
            color: 'rgba(255,255,255,0.9)',
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '0.02em',
          }}
        >
          New episodes on calm ambition and boundaries
        </div>
      ) : (
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
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '0.02em',
          }}
        >
          New episodes on calm ambition and boundaries
        </div>
      )}
    </AbsoluteFill>
  );
};

const SceneLayer: React.FC<{
  scene: RemotionScene;
  durationInFrames: number;
  isPortrait: boolean;
  fps: number;
}> = ({scene, durationInFrames, isPortrait, fps: _fps}) => {
  const frame = useCurrentFrame();
  const transform = getSceneTransform(scene, frame, durationInFrames);
  const sceneOpacity = interpolate(frame, [0, 8, durationInFrames - 8, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{overflow: 'hidden', opacity: sceneOpacity}}>
      <Img
        src={resolveAssetSrc(scene.imageSrc)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform,
          transformOrigin: 'center center',
          willChange: 'transform',
        }}
      />
      <AbsoluteFill
        style={{
          background: isPortrait
            ? 'linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.18))'
            : 'linear-gradient(180deg, rgba(0,0,0,0.06), rgba(0,0,0,0.12))',
        }}
      />
    </AbsoluteFill>
  );
};

export {StoicVideo};
