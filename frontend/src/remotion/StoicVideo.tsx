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
import type {RemotionPlatform, RemotionRenderProps, RemotionScene, RemotionSubtitle} from './types';

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
  lines: TimedWord[][];
  words: TimedWord[];
  hasWordTimings: boolean;
};

const getPlatform = (mode: RemotionRenderProps['mode'], platform?: RemotionPlatform) => {
  return platform ?? (mode === 'portrait' ? 'tiktok' : 'youtube');
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

const layoutCaptionLines = (words: TimedWord[], isTikTok: boolean): TimedWord[][] => {
  if (words.length === 0) {
    return [];
  }

  const maxCharsPerLine = isTikTok ? 14 : 22;
  const maxLines = isTikTok ? 3 : 2;
  const lines: TimedWord[][] = [];
  let currentLine: TimedWord[] = [];
  let currentChars = 0;

  for (const word of words) {
    const wordChars = word.text.length + (currentLine.length > 0 ? 1 : 0);
    const wouldOverflow = currentLine.length > 0 && currentChars + wordChars > maxCharsPerLine;
    if (wouldOverflow && lines.length < maxLines - 1) {
      lines.push(currentLine);
      currentLine = [word];
      currentChars = word.text.length;
    } else {
      currentLine.push(word);
      currentChars += wordChars;
    }
  }

  if (currentLine.length > 0) {
    lines.push(currentLine);
  }

  return lines;
};

const chunkWordsForCaptions = (
  words: TimedWord[],
  isTikTok: boolean,
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
        lines: layoutCaptionLines(words, isTikTok),
        words: [...words],
        hasWordTimings: false,
      },
    ];
  }

  const maxWordsPerChunk = isTikTok ? 4 : 7;
  const chunks: CaptionChunk[] = [];
  let currentChunk: TimedWord[] = [];

  const flushChunk = () => {
    if (currentChunk.length === 0) {
      return;
    }

    chunks.push({
      startTime: currentChunk[0].startTime,
      endTime: currentChunk[currentChunk.length - 1].endTime,
      lines: layoutCaptionLines(currentChunk, isTikTok),
      words: [...currentChunk],
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
      (currentChunk.length >= 2 && pauseBeforeWord >= (isTikTok ? 0.22 : 0.3)) ||
      (currentChunk.length >= 3 && punctuationBreak)
    ) {
      flushChunk();
    }

    currentChunk.push(word);
  }

  flushChunk();
  return chunks;
};

const buildCaptionChunks = (subtitles: RemotionSubtitle[], isTikTok: boolean): CaptionChunk[] => {
  return subtitles.flatMap((subtitle) => {
    const normalized = normalizeSubtitleWords(subtitle);
    return chunkWordsForCaptions(normalized.words, isTikTok, normalized.hasWordTimings);
  });
};

const StoicVideo: React.FC<RemotionRenderProps> = ({
  title,
  topic,
  channelName,
  mode,
  platform,
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
  const resolvedPlatform = getPlatform(mode, platform);
  const isTikTok = resolvedPlatform === 'tiktok';
  const totalFrames = Math.max(1, Math.round(durationInSeconds * fps));
  const captionChunks = useMemo(() => buildCaptionChunks(subtitles, isTikTok), [subtitles, isTikTok]);

  const subtitleCardStyle: React.CSSProperties = useMemo(
    () => ({
      position: 'absolute',
      left: isTikTok ? '8%' : '14%',
      right: isTikTok ? '8%' : '14%',
      top: isTikTok ? '56%' : '68%',
      transform: 'translateY(-50%)',
      zIndex: 30,
      padding: isTikTok ? '24px 24px 28px' : '18px 24px 20px',
      borderRadius: isTikTok ? 30 : 18,
      background: isTikTok
        ? 'linear-gradient(180deg, rgba(13,13,25,0.24), rgba(13,13,25,0.76))'
        : 'linear-gradient(180deg, rgba(4,10,20,0.2), rgba(4,10,20,0.58))',
      border: isTikTok ? '1px solid rgba(255,255,255,0.1)' : '1px solid rgba(255,255,255,0.08)',
      boxShadow: isTikTok ? '0 24px 90px rgba(0,0,0,0.48)' : '0 16px 50px rgba(0,0,0,0.32)',
      backdropFilter: 'blur(18px)',
    }),
    [isTikTok],
  );

  const channelStyle: React.CSSProperties = {
    position: 'absolute',
    top: isTikTok ? 88 : 42,
    left: isTikTok ? 30 : 54,
    zIndex: 25,
    padding: isTikTok ? '10px 15px' : '10px 18px',
    borderRadius: isTikTok ? 18 : 999,
    background: isTikTok ? 'rgba(7,10,20,0.48)' : 'rgba(7,10,20,0.38)',
    border: '1px solid rgba(255,255,255,0.12)',
    fontSize: isTikTok ? 22 : 26,
    fontWeight: 800,
    letterSpacing: isTikTok ? '0.08em' : '0.04em',
    color: TEXT_COLOR,
    textTransform: 'uppercase',
    boxShadow: '0 10px 30px rgba(0,0,0,0.28)',
  };

  const titleStyle: React.CSSProperties = {
    position: 'absolute',
    top: isTikTok ? 154 : 110,
    left: isTikTok ? 30 : 54,
    right: isTikTok ? 52 : 54,
    zIndex: 25,
    fontSize: isTikTok ? 58 : 48,
    lineHeight: isTikTok ? 0.98 : 1.02,
    fontWeight: 950,
    letterSpacing: '-0.05em',
    color: TEXT_COLOR,
    textShadow: '0 8px 28px rgba(0,0,0,0.45)',
    maxWidth: isTikTok ? '86%' : '58%',
  };

  const kickerStyle: React.CSSProperties = {
    position: 'absolute',
    top: isTikTok ? 250 : 188,
    left: isTikTok ? 30 : 54,
    zIndex: 25,
    padding: isTikTok ? '12px 16px' : '10px 14px',
    borderRadius: 999,
    background: isTikTok
      ? 'linear-gradient(135deg, rgba(251,113,133,0.85), rgba(245,158,11,0.92))'
      : 'rgba(255,255,255,0.12)',
    color: isTikTok ? '#111827' : 'rgba(255,255,255,0.92)',
    fontSize: isTikTok ? 22 : 20,
    fontWeight: 900,
    letterSpacing: isTikTok ? '0.03em' : '0.02em',
    textTransform: 'uppercase',
  };

  const progressStyle: React.CSSProperties = {
    position: 'absolute',
    top: isTikTok ? 50 : 30,
    left: isTikTok ? '5.5%' : '18%',
    width: isTikTok ? '89%' : '64%',
    height: isTikTok ? 8 : 5,
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
    top: isTikTok ? 42 : 28,
    right: isTikTok ? 24 : 34,
    width: isTikTok ? 72 : 108,
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
      isTikTok
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
              isTikTok={isTikTok}
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
      <div style={kickerStyle}>{isTikTok ? 'Mindset reset' : 'Practical Stoicism for modern work'}</div>

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

        const activeWordIndex = chunk.hasWordTimings
          ? chunk.words.findIndex((word, wordIndex) => {
              const wordStart = Math.round(word.startTime * fps);
              const nextStart =
                wordIndex === chunk.words.length - 1
                  ? endFrame
                  : Math.round(chunk.words[wordIndex + 1].startTime * fps);
              return frame >= wordStart && frame < nextStart;
            })
          : -1;

        let runningWordIndex = 0;

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
                flexDirection: 'column',
                alignItems: 'center',
                gap: isTikTok ? 8 : 6,
                color: TEXT_COLOR,
                textShadow: '0 6px 26px rgba(0,0,0,0.4)',
              }}
            >
              {chunk.lines.map((line, lineIndex) => {
                const lineStartIndex = runningWordIndex;
                runningWordIndex += line.length;
                return (
                  <div
                    key={`${idx}-line-${lineIndex}`}
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      justifyContent: 'center',
                      gap: isTikTok ? '8px 10px' : '8px 12px',
                      fontSize: isTikTok ? 56 : 46,
                      lineHeight: isTikTok ? 1.02 : 1.08,
                      fontWeight: 950,
                      letterSpacing: '-0.04em',
                      textAlign: 'center',
                    }}
                  >
                    {line.map((word, wordIndexInLine) => {
                      const absoluteWordIndex = lineStartIndex + wordIndexInLine;
                      const isActiveWord = absoluteWordIndex === activeWordIndex;
                      return (
                        <span
                          key={`${idx}-${absoluteWordIndex}`}
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
              padding: isTikTok ? '64px' : '80px',
              background: isTikTok
                ? 'linear-gradient(135deg, rgba(5,8,22,0.9), rgba(17,24,39,0.88), rgba(88,28,135,0.82))'
                : 'linear-gradient(135deg, rgba(5,8,22,0.94), rgba(10,24,40,0.92), rgba(18,58,92,0.84))',
              zIndex: 40,
            }}
          >
            <div
              style={{
                padding: isTikTok ? '18px 22px' : '14px 20px',
                borderRadius: 999,
                border: '1px solid rgba(255,255,255,0.14)',
                background: 'rgba(255,255,255,0.06)',
                color: HIGHLIGHT_COLOR,
                textTransform: 'uppercase',
                letterSpacing: isTikTok ? '0.18em' : '0.12em',
                fontWeight: 800,
                marginBottom: isTikTok ? 22 : 18,
                transform: `scale(${interpolate(ctaPulse, [0, 1], [0.92, 1])})`,
              }}
            >
              {isTikTok ? channelName : 'Stoic Modernized on YouTube'}
            </div>
            <div
              style={{
                color: TEXT_COLOR,
                fontSize: isTikTok ? 84 : 72,
                fontWeight: 950,
                lineHeight: 0.95,
                letterSpacing: '-0.05em',
                textAlign: 'center',
                marginBottom: isTikTok ? 24 : 18,
                textShadow: '0 12px 40px rgba(0,0,0,0.35)',
                transform: `translateY(${interpolate(ctaPulse, [0, 1], [24, 0])}px)`,
              }}
            >
              {isTikTok ? (
                <>
                  subscribe to
                  <br />
                  @stoic-modernized
                </>
              ) : (
                <>
                  subscribe to
                  <br />
                  @stoic-modernized
                </>
              )}
            </div>
            <div
              style={{
                maxWidth: isTikTok ? '88%' : '62%',
                textAlign: 'center',
                color: 'rgba(255,255,255,0.92)',
                fontSize: isTikTok ? 32 : 28,
                lineHeight: 1.2,
                fontWeight: 600,
              }}
            >
              {ctaText}
            </div>
          </AbsoluteFill>
        </Sequence>
      ) : null}

      {isTikTok ? (
        <div
          style={{
            position: 'absolute',
            right: 24,
            top: 116,
            zIndex: 30,
            writingMode: 'vertical-rl',
            textOrientation: 'mixed',
            color: 'rgba(255,255,255,0.58)',
            fontSize: 18,
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            fontWeight: 700,
          }}
        >
          {channelName}
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
  isTikTok: boolean;
  fps: number;
}> = ({scene, durationInFrames, isTikTok, fps}) => {
  const frame = useCurrentFrame();
  const entrance = spring({
    fps,
    frame,
    config: {damping: 200, stiffness: 140},
  });
  const transform = getSceneTransform(scene, frame, durationInFrames);
  const overlayY = interpolate(entrance, [0, 1], [16, 0]);
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
          background: isTikTok
            ? 'linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.18))'
            : 'linear-gradient(180deg, rgba(0,0,0,0.06), rgba(0,0,0,0.12))',
        }}
      />
      {scene.textOverlay ? (
        <div
          style={{
            position: 'absolute',
            top: isTikTok ? 290 : 236,
            left: isTikTok ? 30 : 54,
            zIndex: 12,
            padding: isTikTok ? '14px 20px' : '12px 18px',
            borderRadius: isTikTok ? 18 : 14,
            background: isTikTok
              ? 'linear-gradient(135deg, rgba(17,24,39,0.62), rgba(88,28,135,0.42))'
              : 'linear-gradient(135deg, rgba(4,12,24,0.68), rgba(15,23,42,0.52))',
            border: '1px solid rgba(255,255,255,0.12)',
            color: TEXT_COLOR,
            fontSize: isTikTok ? 28 : 24,
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
