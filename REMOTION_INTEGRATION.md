# Remotion Integration - Production Video Renderer

## Overview

Remotion v4 integration for generating production-quality YouTube/TikTok videos with high-quality effects including:
- Animated zoom/pan effects on images
- Kinetic typography subtitles
- Progress bars (portrait mode)
- Channel branding overlays
- Professional visual effects

## Architecture

```
Pipeline Data (scenes, audio, subtitles)
         ↓
  RemotionRenderer (Python)
         ↓
  Props JSON + Assets
         ↓
  Remotion CLI (Node.js)
         ↓
  H.264 Video Output
```

## Setup

### Dependencies

```bash
cd frontend
npm install remotion@4.0.448 @remotion/cli@4.0.448 @remotion/renderer@4.0.448 zod
```

### Components

- `frontend/src/remotion/index.ts` - Remotion entry point
- `frontend/src/remotion/Root.tsx` - Composition definitions (Landscape/Portrait)
- `frontend/src/remotion/StoicVideo.tsx` - Main video composition with effects
- `frontend/src/remotion/types.ts` - TypeScript types
- `frontend/src/remotion/sample-props.ts` - Sample props for development
- `src/stages/remotion_renderer.py` - Python wrapper for Remotion CLI

## Usage

### From Python Pipeline

```python
from src.stages.remotion_renderer import RemotionRenderer

renderer = RemotionRenderer(
    job_id='job-uuid',
    frontend_dir=Path('/path/to/frontend'),
    width=1080,
    height=1920,
    fps=30,
    mode='portrait'  # or 'landscape'
)

result = renderer.run()
print(f"Video: {result['video_path']}")
```

### From CLI

```bash
python3 -m src.main render <job-id> --renderer remotion --video-mode short
```

## Asset Handling

Assets are copied to `frontend/public/` directory before render:

- Images: `frontend/public/images/scene_XXX.jpg`
- Audio: `frontend/public/audio/narration.mp3`
- Subtitles: `frontend/public/subtitles/subtitles.json`

The renderer uses `staticFile()` to bundle assets into the Remotion bundle.

## Output Quality

### Portrait (TikTok/Reels/Shorts)
- Resolution: 1080x1920
- Aspect Ratio: 9:16
- Features: Progress bar, vertical-optimized subtitles

### Landscape (YouTube)
- Resolution: 1920x1080
- Aspect Ratio: 16:9
- Features: Horizontal layout, standard subtitles

## Rendering

Remotion uses Chrome Headless Shell for rendering:
- **Codec:** H.264 (libx264)
- **Audio:** AAC
- **Concurrency:** 8 threads (default)
- **Quality:** High (uses Chrome's renderer)

### Performance
- 1080p @ 30fps: ~10-15 seconds per second of video
- Can be optimized with `--concurrency` flag

## Visual Effects

### Zoom Effect
- Smooth CSS transform on images
- Starts at scale 1.0, ends at 1.1
- Applied per scene with `animationStyle: 'zoom'`

### Pan Effects
- Horizontal panning for dynamic visuals
- Options: `pan-left`, `pan-right`

### Subtitles
- Kinetic typography (word-by-word highlighting)
- Shadow effects for readability
- Responsive font sizes (landscape vs portrait)

### Overlays
- Text overlays with semi-transparent backgrounds
- Channel name watermark
- Progress bar (portrait only)
- CTA screen at end

## Troubleshooting

### Assets Not Loading
- Ensure assets are in `frontend/public/` directory
- Check file permissions
- Verify `staticFile()` is used for all assets

### Render Fails at Frame 0
- Check Chrome Headless Shell installation
- Verify all assets exist
- Check props JSON structure

### Video Duration Mismatch
- Composition duration = max(scene end times)
- Check `durationInSeconds` in props
- Ensure scenes don't have gaps

## Future Improvements

- [ ] Dynamic duration calculation based on props
- [ ] More animation presets (fade, slide, rotate)
- [ ] Multi-track audio support
- [ ] Logo watermark with transparency
- [ ] Color grading options
- [ ] Custom font support
- [ ] GIF export option
- [ ] Image sequence output

## References

- [Remotion v4 Docs](https://www.remotion.dev/docs/)
- [Remotion CLI Reference](https://www.remotion.dev/docs/cli/render)
- [Remotion Examples](https://github.com/remotion-dev/remotion/tree/main/examples)
