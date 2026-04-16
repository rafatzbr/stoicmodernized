import React, {useMemo} from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  useCurrentFrame,
  staticFile,
} from 'remotion';

type RemotionScene = {
  sceneNumber: number;
  imageSrc: string;
  startTime: number;
  endTime: number;
  narrationSegment: string;
  textOverlay?: string | null;
  animationStyle?: string | null;
};

type RemotionSubtitle = {
  startTime: number;
  endTime: number;
  text: string;
  words?: {startTime: number; endTime: number; text: string}[] | null;
};

type RemotionRenderProps = {
  title: string;
  topic: string;
  channelName: string;
  mode: 'landscape' | 'portrait';
  fps: number;
  durationInSeconds: number;
  audioSrc: string;
  logoSrc?: string | null;
  scenes: RemotionScene[];
  subtitles: RemotionSubtitle[];
  ctaText?: string | null;
};

// Colors
const TEXT_COLOR = '#ffffff';
const HIGHLIGHT_COLOR = '#FFD700';

const resolveAssetSrc = (src: string) => {
  return /^https?:\/\//.test(src) ? src : staticFile(src);
};

// Typography
const CAPTION_FONT_SIZE_LANDSCAPE = 64;
const CAPTION_FONT_SIZE_PORTRAIT = 52;
const OVERLAY_FONT_SIZE_LANDSCAPE = 48;
const OVERLAY_FONT_SIZE_PORTRAIT = 36;

const StoicVideo: React.FC<RemotionRenderProps> = (props) => {
  const frame = useCurrentFrame();
  
  const {mode, fps, scenes, subtitles, durationInSeconds, audioSrc, logoSrc, ctaText} = props;

  const isPortrait = mode === 'portrait';
  const captionFontSize = isPortrait ? CAPTION_FONT_SIZE_PORTRAIT : CAPTION_FONT_SIZE_LANDSCAPE;
  const overlayFontSize = isPortrait ? OVERLAY_FONT_SIZE_PORTRAIT : OVERLAY_FONT_SIZE_LANDSCAPE;
  
  const subtitleStyle: React.CSSProperties = {
    fontSize: captionFontSize,
    fontFamily: 'system-ui, -apple-system, sans-serif',
    fontWeight: 700,
    textAlign: 'center',
    color: TEXT_COLOR,
    textShadow: `${isPortrait ? '0 0 20px' : '0 4px 20px'} #000000`,
    lineHeight: 1.2,
    padding: isPortrait ? '0 40px 60px' : '0 80px 80px',
    maxWidth: isPortrait ? '80%' : '70%',
    margin: 'auto',
    position: 'absolute' as const,
    bottom: isPortrait ? 100 : 60,
    left: 0,
    right: 0,
    zIndex: 10,
  };

  const overlayStyle: React.CSSProperties = {
    fontSize: overlayFontSize,
    fontFamily: 'system-ui, -apple-system, sans-serif',
    fontWeight: 800,
    textAlign: 'center',
    color: TEXT_COLOR,
    textShadow: `${isPortrait ? '0 0 16px' : '0 3px 16px'} #000000`,
    padding: isPortrait ? '10px 20px' : '12px 24px',
    background: 'rgba(0,0,0,0.6)',
    borderRadius: isPortrait ? 12 : 8,
    marginBottom: isPortrait ? 15 : 20,
    display: 'inline-block',
  };

  const progressStyle: React.CSSProperties = useMemo(() => ({
    position: 'absolute' as const,
    top: isPortrait ? 60 : 30,
    left: isPortrait ? '50%' : '50%',
    transform: 'translateX(-50%)',
    height: isPortrait ? 6 : 4,
    background: 'rgba(255,255,255,0.3)',
    borderRadius: isPortrait ? 3 : 2,
    overflow: 'hidden',
    zIndex: 100,
    width: isPortrait ? '80%' : '60%',
  }), [isPortrait]);

  const progressFillStyle: React.CSSProperties = useMemo(() => ({
    height: '100%',
    width: `${(frame / (durationInSeconds * fps)) * 100}%`,
    background: `linear-gradient(90deg, ${HIGHLIGHT_COLOR}, #FFA500)`,
    borderRadius: isPortrait ? 3 : 2,
    transition: 'width 0.1s linear',
  }), [frame, durationInSeconds, fps, isPortrait]);

  const channelStyle: React.CSSProperties = {
    position: 'absolute' as const,
    top: isPortrait ? 80 : 40,
    left: isPortrait ? 40 : 60,
    right: isPortrait ? 40 : 60,
    fontSize: isPortrait ? 28 : 36,
    fontFamily: 'system-ui, -apple-system, sans-serif',
    fontWeight: 700,
    color: TEXT_COLOR,
    textShadow: '0 2px 12px #000000',
    zIndex: 100,
  };

  const logoStyle: React.CSSProperties = {
    position: 'absolute' as const,
    top: isPortrait ? 20 : 10,
    right: isPortrait ? 20 : 30,
    width: isPortrait ? 80 : 120,
    height: 'auto',
    zIndex: 100,
    opacity: 0.8,
  };

  const vignetteStyle: React.CSSProperties = {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'radial-gradient(circle, transparent 40%, rgba(0,0,0,0.4) 100%)',
    pointerEvents: 'none' as const,
    zIndex: 5,
  };

  const ctaStyle: React.CSSProperties = {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    display: 'flex',
    flexDirection: 'column' as const,
    justifyContent: 'center',
    alignItems: 'center',
    background: 'linear-gradient(135deg, #1a1a2e, #16213e)',
    padding: isPortrait ? '60px' : '100px',
    textAlign: 'center' as const,
  };

  const ctaTitleStyle: React.CSSProperties = {
    fontSize: isPortrait ? 56 : 72,
    fontFamily: 'system-ui, -apple-system, sans-serif',
    fontWeight: 800,
    color: TEXT_COLOR,
    marginBottom: isPortrait ? 30 : 40,
    textShadow: '0 4px 24px rgba(0,0,0,0.6)',
  };

  const ctaSubtitleStyle: React.CSSProperties = {
    fontSize: isPortrait ? 32 : 40,
    fontFamily: 'system-ui, -apple-system, sans-serif',
    fontWeight: 600,
    color: 'rgba(255,255,255,0.9)',
    marginBottom: isPortrait ? 20 : 30,
  };

  return (
    <AbsoluteFill style={{background: 'black'}}>
      <Audio src={resolveAssetSrc(audioSrc)} volume={0.15} />
      
      {/* Scenes */}
      {scenes.map((scene) => (
        <Sequence
          key={scene.sceneNumber}
          from={Math.round(scene.startTime * fps)}
          durationInFrames={Math.round((scene.endTime - scene.startTime) * fps)}
        >
          <AbsoluteFill>
            <Img
              src={resolveAssetSrc(scene.imageSrc)}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
            <AbsoluteFill style={{background: 'rgba(0,0,0,0.2)'}} />
            {scene.textOverlay && (
              <AbsoluteFill style={{top: 40, zIndex: 6}}>
                <div style={{...overlayStyle, margin: 'auto'}}>
                  {scene.textOverlay}
                </div>
              </AbsoluteFill>
            )}
            <AbsoluteFill style={vignetteStyle} />
          </AbsoluteFill>
        </Sequence>
      ))}

      {/* Progress bar (portrait only) */}
      {isPortrait && (
        <Sequence from={0} durationInFrames={Math.round(durationInSeconds * fps)}>
          <div style={progressStyle}>
            <div style={progressFillStyle} />
          </div>
        </Sequence>
      )}

      {/* Channel name */}
      <Sequence from={0} durationInFrames={Math.round(durationInSeconds * fps)}>
        <div style={channelStyle}>{props.channelName}</div>
      </Sequence>

      {/* Logo watermark */}
      {logoSrc && (
        <Sequence from={0} durationInFrames={Math.round(durationInSeconds * fps)}>
          <Img src={resolveAssetSrc(logoSrc)} style={logoStyle} />
        </Sequence>
      )}

      {/* Subtitles */}
      <Sequence from={0} durationInFrames={Math.round(durationInSeconds * fps)}>
        {subtitles.map((sub, idx) => {
          const startFrame = Math.round(sub.startTime * fps);
          const endFrame = Math.round(sub.endTime * fps);
          const isActive = frame >= startFrame && frame < endFrame;
          
          if (!isActive) return null;
          
          const words = sub.words || [];
          const activeWordIndex = words.findIndex(
            (w, i) => {
              if (i === words.length - 1) {
                return frame >= Math.round(w.startTime * fps);
              }
              return frame >= Math.round(w.startTime * fps) && frame < Math.round(words[i + 1].startTime * fps);
            }
          );

          const renderText = () => {
            const wordsArr = sub.words || sub.text.split(' ');
            const wordElements = wordsArr.map((w, i) => {
              const wordText = typeof w === 'string' ? w : w.text;
              const isActiveWord = activeWordIndex === i;
              return (
                <span
                  key={i}
                  style={{
                    color: isActiveWord ? HIGHLIGHT_COLOR : TEXT_COLOR,
                    transition: 'color 0.1s ease',
                    marginRight: '4px',
                  }}
                >
                  {wordText}
                </span>
              );
            });
            return <span>{wordElements}</span>;
          };

          return (
            <div key={idx} style={subtitleStyle}>
              {renderText()}
            </div>
          );
        })}
      </Sequence>

      {/* CTA End Card */}
      {ctaText && (
        <Sequence from={Math.max(0, Math.round((durationInSeconds - 3) * fps))} durationInFrames={Math.round(3 * fps)}>
          <div style={ctaStyle}>
            <div style={ctaTitleStyle}>Subscribe</div>
            <div style={ctaSubtitleStyle}>{ctaText}</div>
          </div>
        </Sequence>
      )}
    </AbsoluteFill>
  );
};

export {StoicVideo};
