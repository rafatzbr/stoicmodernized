import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import LaunchRoundedIcon from '@mui/icons-material/LaunchRounded';
import UploadRoundedIcon from '@mui/icons-material/UploadRounded';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Link,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import type { JobAsset, JobDetail } from '../types';

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function isImage(asset: JobAsset) {
  return asset.mime?.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/i.test(asset.relative);
}

function isVideo(asset: JobAsset) {
  return asset.mime?.startsWith('video/') || /\.(mp4|mov|mkv|webm)$/i.test(asset.relative);
}

function isAudio(asset: JobAsset) {
  return asset.mime?.startsWith('audio/') || /\.(mp3|wav|m4a|ogg)$/i.test(asset.relative);
}

function isJson(asset: JobAsset) {
  return asset.mime === 'application/json' || /\.json$/i.test(asset.relative);
}

function isTextLike(asset: JobAsset) {
  return asset.mime?.startsWith('text/') || isJson(asset) || /\.(txt|json|md|py|yaml|yml|srt|log)$/i.test(asset.relative);
}

function formatPreviewText(asset: JobAsset, rawText: string) {
  if (!rawText) return rawText;
  if (isJson(asset)) {
    try {
      return JSON.stringify(JSON.parse(rawText), null, 2);
    } catch {
      return rawText;
    }
  }
  return rawText;
}

function PreviewText({ content }: { content: string }) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 2,
        maxHeight: '70vh',
        overflow: 'auto',
        border: '1px solid',
        borderColor: 'divider',
        bgcolor: '#050505',
        color: '#f5f5f5',
        fontFamily: 'Space Mono, ui-monospace, monospace',
        fontSize: 12,
        lineHeight: 1.75,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {content}
    </Box>
  );
}

function AssetPreview({ asset }: { asset: JobAsset }) {
  const [textContent, setTextContent] = useState('');
  const [loadingText, setLoadingText] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadText() {
      if (!asset.url || !isTextLike(asset)) {
        setTextContent('');
        setTextError(null);
        return;
      }

      setLoadingText(true);
      setTextError(null);

      try {
        const response = await fetch(asset.url);
        if (!response.ok) {
          throw new Error(`Preview failed with ${response.status}`);
        }
        const nextText = await response.text();
        if (!cancelled) {
          setTextContent(formatPreviewText(asset, nextText));
        }
      } catch (error) {
        if (!cancelled) {
          setTextError(error instanceof Error ? error.message : 'Failed to load preview');
        }
      } finally {
        if (!cancelled) {
          setLoadingText(false);
        }
      }
    }

    void loadText();
    return () => {
      cancelled = true;
    };
  }, [asset]);

  if (!asset.url) {
    return <Typography color="text.secondary">No preview URL available for this asset.</Typography>;
  }

  if (isImage(asset)) {
    return <Box component="img" src={asset.url} alt={asset.relative} sx={{ width: '100%', maxHeight: '70vh', objectFit: 'contain' }} />;
  }

  if (isVideo(asset)) {
    return <Box component="video" src={asset.url} controls sx={{ width: '100%', maxHeight: '70vh', bgcolor: '#000' }} />;
  }

  if (isAudio(asset)) {
    return <Box component="audio" src={asset.url} controls sx={{ width: '100%' }} />;
  }

  if (isTextLike(asset)) {
    if (loadingText) return <Typography color="text.secondary">Loading preview…</Typography>;
    if (textError) return <Typography color="error.main">{textError}</Typography>;
    return <PreviewText content={textContent || 'File is empty.'} />;
  }

  return (
    <Button component={Link} href={asset.url} target="_blank" rel="noreferrer" startIcon={<LaunchRoundedIcon />}>
      Open in new tab
    </Button>
  );
}

export function JobAssets({
  jobDetail,
  onRefresh,
  onRerunSteps,
  onFullRerun,
  onUploadAsset,
  rerunBusy,
}: {
  jobDetail: JobDetail | null;
  onRefresh: () => void;
  onRerunSteps: (steps: string[], rendererOverride?: string) => void;
  onFullRerun: () => void;
  onUploadAsset: (assetPath: string) => void;
  rerunBusy: boolean;
}) {
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);

  const assetSummary = useMemo(() => {
    if (!jobDetail) return null;
    return {
      images: jobDetail.assets.filter(isImage).length,
      videos: jobDetail.assets.filter(isVideo).length,
      audio: jobDetail.assets.filter(isAudio).length,
    };
  }, [jobDetail]);

  const uploadableVideos = useMemo(() => {
    if (!jobDetail) return [];
    const score = (asset: JobAsset) => {
      const relative = asset.relative.toLowerCase();
      if (relative.includes('remotion')) return 0;
      if (relative.includes('final.mp4')) return 1;
      return 2;
    };
    return jobDetail.assets.filter(isVideo).sort((a, b) => score(a) - score(b) || a.relative.localeCompare(b.relative));
  }, [jobDetail]);

  const normalizedPreviewIndex = useMemo(() => {
    if (previewIndex === null || !jobDetail || jobDetail.assets.length === 0) return null;
    return Math.min(previewIndex, jobDetail.assets.length - 1);
  }, [jobDetail, previewIndex]);

  const previewAsset = normalizedPreviewIndex !== null && jobDetail ? jobDetail.assets[normalizedPreviewIndex] ?? null : null;
  const canGoPrevious = normalizedPreviewIndex !== null && normalizedPreviewIndex > 0;
  const canGoNext = normalizedPreviewIndex !== null && !!jobDetail && normalizedPreviewIndex < jobDetail.assets.length - 1;

  return (
    <>
      <Stack spacing={3}>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'flex-end' }} spacing={2}>
          <Box>
            <Typography variant="overline" color="text.secondary">
              INSPECTOR
            </Typography>
            <Typography variant="h5">Selected job</Typography>
            <Typography variant="body2" color="text.secondary">
              Review outputs, rerun the right slice, or push the final video.
            </Typography>
          </Box>
          <Button variant="outlined" size="small" onClick={onRefresh}>
            REFRESH
          </Button>
        </Stack>

        {!jobDetail ? (
          <Typography variant="body2" color="text.secondary">
            Pick a job on the left to inspect outputs.
          </Typography>
        ) : (
          <Stack spacing={2.5}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
              <Stack spacing={0.5}>
                <Typography variant="body1" sx={{ fontWeight: 700 }}>
                  {jobDetail.topic}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {(jobDetail.channel_name ?? jobDetail.channel ?? 'channel').toUpperCase()} · {(jobDetail.channel_handle ?? '').toUpperCase()}
                </Typography>
                <Typography variant="caption" color="text.disabled">
                  {jobDetail.job_id}
                </Typography>
              </Stack>
              <Stack spacing={0.5} alignItems={{ xs: 'flex-start', md: 'flex-end' }}>
                <Typography variant="caption" color="text.secondary">
                  STATUS
                </Typography>
                <Typography variant="body2">{jobDetail.status.toUpperCase()}</Typography>
                {assetSummary ? (
                  <Typography variant="caption" color="text.secondary">
                    {jobDetail.assets.length} files · {assetSummary.images} images · {assetSummary.audio} audio · {assetSummary.videos} videos
                  </Typography>
                ) : null}
              </Stack>
            </Stack>

            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Button variant="outlined" disabled={rerunBusy} onClick={() => onRerunSteps(['tts', 'subtitles', 'render', 'metadata'])}>RERUN TTS→RENDER</Button>
              <Button variant="outlined" disabled={rerunBusy} onClick={() => onRerunSteps(['images', 'subtitles', 'render', 'metadata'])}>RERUN IMAGES→RENDER</Button>
              <Button variant="outlined" disabled={rerunBusy} onClick={() => onRerunSteps(['subtitles', 'render', 'metadata'])}>RERUN SUBTITLES→RENDER</Button>
              <Button variant="outlined" disabled={rerunBusy} onClick={() => onRerunSteps(['render', 'metadata'])}>RERENDER</Button>
              <Button variant="outlined" disabled={rerunBusy} onClick={() => onRerunSteps(['render', 'metadata'], 'remotion')}>REMOTION ONLY</Button>
              <Button variant="outlined" disabled={rerunBusy} onClick={() => onRerunSteps(['render', 'metadata'], 'ffmpeg')}>FFMPEG ONLY</Button>
            </Stack>

            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Button variant="contained" disabled={rerunBusy} onClick={onFullRerun}>RERUN ENTIRE PIPELINE</Button>
              <Button
                variant="contained"
                color="secondary"
                startIcon={<UploadRoundedIcon />}
                disabled={rerunBusy || uploadableVideos.length === 0}
                onClick={() => setUploadDialogOpen(true)}
              >
                UPLOAD TO YOUTUBE
              </Button>
            </Stack>

            <Stack spacing={1}>
              {jobDetail.assets.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No files found for this job yet.
                </Typography>
              ) : (
                jobDetail.assets.map((asset, index) => (
                  <Stack
                    key={asset.path}
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                    spacing={1}
                    sx={{ border: '1px solid', borderColor: 'divider', px: 1.5, py: 1.25 }}
                  >
                    <Box sx={{ minWidth: 0 }}>
                      <Link
                        component="button"
                        type="button"
                        underline="hover"
                        color="inherit"
                        onClick={() => setPreviewIndex(index)}
                        sx={{ textAlign: 'left', fontWeight: 600 }}
                      >
                        {asset.relative}
                      </Link>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                        {formatBytes(asset.size)}{asset.mime ? ` · ${asset.mime}` : ''}
                      </Typography>
                    </Box>
                    {asset.url ? (
                      <Button size="small" component={Link} href={asset.url} target="_blank" rel="noreferrer" startIcon={<DownloadRoundedIcon />}>
                        OPEN
                      </Button>
                    ) : null}
                  </Stack>
                ))
              )}
            </Stack>
          </Stack>
        )}
      </Stack>

      <Dialog open={uploadDialogOpen} onClose={() => setUploadDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Choose a video to upload</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.25}>
            {uploadableVideos.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No video files are available for this job yet.
              </Typography>
            ) : (
              uploadableVideos.map((asset) => (
                <Button
                  key={asset.path}
                  variant="outlined"
                  onClick={() => {
                    onUploadAsset(asset.relative);
                    setUploadDialogOpen(false);
                  }}
                  sx={{ justifyContent: 'space-between', py: 1.25 }}
                >
                  <Stack alignItems="flex-start" sx={{ textAlign: 'left' }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {asset.relative.toLowerCase().includes('remotion')
                        ? 'REMOTION RENDER'
                        : asset.relative.toLowerCase().includes('final.mp4')
                          ? 'FINAL VIDEO'
                          : 'VIDEO FILE'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {asset.relative} · {formatBytes(asset.size)}
                    </Typography>
                  </Stack>
                </Button>
              ))
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadDialogOpen(false)}>Cancel</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(previewAsset)} onClose={() => setPreviewIndex(null)} maxWidth="lg" fullWidth>
        <DialogTitle>
          <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="space-between">
            <Stack spacing={0.25} sx={{ minWidth: 0 }}>
              <Typography variant="inherit" noWrap>
                {previewAsset?.relative ?? 'Asset preview'}
              </Typography>
              {previewAsset && jobDetail ? (
                <Typography variant="caption" color="text.secondary">
                  {normalizedPreviewIndex! + 1} / {jobDetail.assets.length}
                </Typography>
              ) : null}
            </Stack>
            <Stack direction="row" spacing={0.5}>
              <IconButton onClick={() => canGoPrevious && setPreviewIndex((value) => (value === null ? value : value - 1))} disabled={!canGoPrevious}>
                <ChevronLeftRoundedIcon />
              </IconButton>
              <IconButton onClick={() => canGoNext && setPreviewIndex((value) => (value === null ? value : value + 1))} disabled={!canGoNext}>
                <ChevronRightRoundedIcon />
              </IconButton>
            </Stack>
          </Stack>
        </DialogTitle>
        <DialogContent dividers>{previewAsset ? <AssetPreview asset={previewAsset} /> : null}</DialogContent>
        <DialogActions>
          <Button onClick={() => canGoPrevious && setPreviewIndex((value) => (value === null ? value : value - 1))} disabled={!canGoPrevious}>Previous</Button>
          <Button onClick={() => canGoNext && setPreviewIndex((value) => (value === null ? value : value + 1))} disabled={!canGoNext}>Next</Button>
          <Button onClick={() => setPreviewIndex(null)}>Close</Button>
          {previewAsset?.url ? (
            <Button component={Link} href={previewAsset.url} target="_blank" rel="noreferrer" startIcon={<LaunchRoundedIcon />}>
              Open in new tab
            </Button>
          ) : null}
        </DialogActions>
      </Dialog>
    </>
  );
}
