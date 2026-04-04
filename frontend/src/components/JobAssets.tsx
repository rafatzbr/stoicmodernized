import ArticleRoundedIcon from '@mui/icons-material/ArticleRounded';
import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import FolderOpenRoundedIcon from '@mui/icons-material/FolderOpenRounded';
import LaunchRoundedIcon from '@mui/icons-material/LaunchRounded';
import MovieRoundedIcon from '@mui/icons-material/MovieRounded';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Link,
  List,
  ListItem,
  ListItemText,
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

function renderAssetIcon(relativePath: string) {
  if (/\.(mp4|mov|mkv)$/i.test(relativePath)) {
    return <MovieRoundedIcon color="secondary" fontSize="small" />;
  }

  return <ArticleRoundedIcon color="action" fontSize="small" />;
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
  return (
    asset.mime?.startsWith('text/') ||
    isJson(asset) ||
    /\.(txt|json|md|py|yaml|yml|srt|log)$/i.test(asset.relative)
  );
}

function formatPreviewText(asset: JobAsset, rawText: string) {
  if (!rawText) {
    return rawText;
  }

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
  const lines = useMemo(() => content.split('\n'), [content]);

  return (
    <Box
      sx={{
        maxHeight: '70vh',
        overflow: 'auto',
        borderRadius: 2,
        bgcolor: 'rgba(7, 10, 19, 0.92)',
        color: '#d8e1ff',
        border: '1px solid',
        borderColor: 'divider',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 13,
        lineHeight: 1.6,
      }}
    >
      <Box sx={{ width: '100%' }}>
        {lines.map((line, index) => (
          <Box
            key={`${index + 1}-${line.slice(0, 12)}`}
            sx={{
              display: 'grid',
              gridTemplateColumns: '56px minmax(0, 1fr)',
              alignItems: 'start',
            }}
          >
            <Box
              sx={{
                userSelect: 'none',
                px: 1.5,
                py: 0.1,
                textAlign: 'right',
                color: 'rgba(216, 225, 255, 0.45)',
                borderRight: '1px solid rgba(216, 225, 255, 0.08)',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              {index + 1}
            </Box>
            <Box sx={{ px: 2, py: 0.1, whiteSpace: 'pre-wrap', wordBreak: 'break-word', minWidth: 0 }}>
              {line || ' '}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function AssetPreview({ asset }: { asset: JobAsset }) {
  const [textContent, setTextContent] = useState<string>('');
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
    return (
      <Box
        component="img"
        src={asset.url}
        alt={asset.relative}
        sx={{ width: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: 2, bgcolor: 'rgba(255,255,255,0.03)' }}
      />
    );
  }

  if (isVideo(asset)) {
    return <Box component="video" src={asset.url} controls sx={{ width: '100%', maxHeight: '70vh', borderRadius: 2, bgcolor: '#000' }} />;
  }

  if (isAudio(asset)) {
    return (
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          Audio preview
        </Typography>
        <Box component="audio" src={asset.url} controls sx={{ width: '100%' }} />
      </Stack>
    );
  }

  if (isTextLike(asset)) {
    if (loadingText) {
      return <Typography color="text.secondary">Loading preview…</Typography>;
    }

    if (textError) {
      return <Typography color="error.main">{textError}</Typography>;
    }

    return <PreviewText content={textContent || 'File is empty.'} />;
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Inline preview is not available for this file type.
      </Typography>
      <Button component={Link} href={asset.url} target="_blank" rel="noreferrer" startIcon={<LaunchRoundedIcon />}>
        Open in new tab
      </Button>
    </Stack>
  );
}

export function JobAssets({
  jobDetail,
  onRefresh,
  onRerunSteps,
  rerunBusy,
}: {
  jobDetail: JobDetail | null;
  onRefresh: () => void;
  onRerunSteps: (steps: string[]) => void;
  rerunBusy: boolean;
}) {
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  const assetSummary = useMemo(() => {
    if (!jobDetail) {
      return null;
    }

    const images = jobDetail.assets.filter(isImage).length;
    const videos = jobDetail.assets.filter(isVideo).length;
    const audio = jobDetail.assets.filter(isAudio).length;

    return { images, videos, audio };
  }, [jobDetail]);

  const normalizedPreviewIndex = useMemo(() => {
    if (previewIndex === null || !jobDetail || jobDetail.assets.length === 0) {
      return null;
    }

    return Math.min(previewIndex, jobDetail.assets.length - 1);
  }, [jobDetail, previewIndex]);

  const previewAsset = normalizedPreviewIndex !== null && jobDetail ? jobDetail.assets[normalizedPreviewIndex] ?? null : null;
  const canGoPrevious = normalizedPreviewIndex !== null && normalizedPreviewIndex > 0;
  const canGoNext = normalizedPreviewIndex !== null && !!jobDetail && normalizedPreviewIndex < jobDetail.assets.length - 1;

  return (
    <>
      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
              <div>
                <Typography variant="overline" color="secondary.main">
                  Output inspection
                </Typography>
                <Typography variant="h6">Selected job assets</Typography>
              </div>
              <Button size="small" startIcon={<RefreshRoundedIcon />} onClick={onRefresh}>
                Refresh
              </Button>
            </Stack>

            <Stack spacing={1.5}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} useFlexGap flexWrap="wrap" alignItems={{ xs: 'stretch', sm: 'center' }}>
                <Typography variant="body2" color="text.secondary" sx={{ mr: { sm: 1 } }}>
                  Quick reruns
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!jobDetail || rerunBusy}
                  onClick={() => onRerunSteps(['tts', 'subtitles', 'render', 'metadata'])}
                >
                  Rerun TTS→Render
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!jobDetail || rerunBusy}
                  onClick={() => onRerunSteps(['images', 'subtitles', 'render', 'metadata'])}
                >
                  Rerun Images→Render
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!jobDetail || rerunBusy}
                  onClick={() => onRerunSteps(['subtitles', 'render', 'metadata'])}
                >
                  Rerun Subtitles→Render
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!jobDetail || rerunBusy}
                  onClick={() => onRerunSteps(['render', 'metadata'])}
                >
                  Rerun Render
                </Button>
              </Stack>

              {!jobDetail ? (
                <Stack spacing={1} alignItems="center" sx={{ py: 5, textAlign: 'center' }}>
                  <FolderOpenRoundedIcon color="disabled" />
                  <Typography variant="body1">No job selected</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Pick a job from the list to inspect generated files and enable quick reruns.
                  </Typography>
                </Stack>
              ) : (
                <>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
                    <Chip label={jobDetail.status} color={jobDetail.status === 'completed' ? 'success' : 'default'} size="small" />
                    <Chip label={jobDetail.job_id} size="small" variant="outlined" />
                    <Chip label={`${jobDetail.assets.length} assets`} size="small" variant="outlined" />
                    {assetSummary ? <Chip label={`${assetSummary.images} images • ${assetSummary.audio} audio • ${assetSummary.videos} video`} size="small" variant="outlined" /> : null}
                  </Stack>

                  <Divider />

                  <List disablePadding sx={{ display: 'grid', gap: 1 }}>
                  {jobDetail.assets.length === 0 ? (
                    <Box sx={{ py: 2 }}>
                      <Typography variant="body2" color="text.secondary">
                        No files found for this job yet.
                      </Typography>
                    </Box>
                  ) : (
                    jobDetail.assets.map((asset, index) => (
                      <ListItem
                        key={asset.path}
                        divider={false}
                        secondaryAction={
                          asset.url ? (
                            <Button
                              size="small"
                              component={Link}
                              href={asset.url}
                              target="_blank"
                              rel="noreferrer"
                              startIcon={<DownloadRoundedIcon />}
                            >
                              Open
                            </Button>
                          ) : null
                        }
                        sx={{
                          px: 1.5,
                          py: 1,
                          borderRadius: 2,
                          border: '1px solid',
                          borderColor: 'divider',
                        }}
                      >
                        <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ pr: 10, minWidth: 0 }}>
                          {renderAssetIcon(asset.relative)}
                          <ListItemText
                            primary={
                              asset.url ? (
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
                              ) : (
                                asset.relative
                              )
                            }
                            secondary={`${formatBytes(asset.size)}${asset.mime ? ` • ${asset.mime}` : ''}`}
                          />
                        </Stack>
                      </ListItem>
                    ))
                  )}
                </List>
              </>
            )}
          </Stack>
        </Stack>
      </CardContent>
      </Card>

      <Dialog open={Boolean(previewAsset)} onClose={() => setPreviewIndex(null)} maxWidth="lg" fullWidth>
        <DialogTitle>
          <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="space-between">
            <Stack spacing={0.25} sx={{ minWidth: 0 }}>
              <Typography variant="inherit" noWrap>
                {previewAsset?.relative ?? 'Asset preview'}
              </Typography>
              {previewAsset && jobDetail ? (
                <Typography variant="caption" color="text.secondary">
                  Asset {normalizedPreviewIndex! + 1} of {jobDetail.assets.length}
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
        <DialogContent dividers>
          {previewAsset ? <AssetPreview asset={previewAsset} /> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => canGoPrevious && setPreviewIndex((value) => (value === null ? value : value - 1))} disabled={!canGoPrevious}>
            Previous
          </Button>
          <Button onClick={() => canGoNext && setPreviewIndex((value) => (value === null ? value : value + 1))} disabled={!canGoNext}>
            Next
          </Button>
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
