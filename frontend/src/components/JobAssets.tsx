import ArticleRoundedIcon from '@mui/icons-material/ArticleRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import FolderOpenRoundedIcon from '@mui/icons-material/FolderOpenRounded';
import LaunchRoundedIcon from '@mui/icons-material/LaunchRounded';
import MovieRoundedIcon from '@mui/icons-material/MovieRounded';
import VisibilityRoundedIcon from '@mui/icons-material/VisibilityRounded';
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

function isTextLike(asset: JobAsset) {
  return (
    asset.mime?.startsWith('text/') ||
    asset.mime === 'application/json' ||
    /\.(txt|json|md|py|yaml|yml|srt|log)$/i.test(asset.relative)
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
          setTextContent(nextText);
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

    return (
      <Box
        component="pre"
        sx={{
          mb: 0,
          p: 2,
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
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {textContent || 'File is empty.'}
      </Box>
    );
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

export function JobAssets({ jobDetail }: { jobDetail: JobDetail | null }) {
  const [previewAsset, setPreviewAsset] = useState<JobAsset | null>(null);

  const assetSummary = useMemo(() => {
    if (!jobDetail) {
      return null;
    }

    const images = jobDetail.assets.filter(isImage).length;
    const videos = jobDetail.assets.filter(isVideo).length;
    const audio = jobDetail.assets.filter(isAudio).length;

    return { images, videos, audio };
  }, [jobDetail]);

  return (
    <>
      <Card>
        <CardContent>
          <Stack spacing={2}>
            <div>
              <Typography variant="overline" color="secondary.main">
                Output inspection
              </Typography>
              <Typography variant="h6">Selected job assets</Typography>
            </div>

            {!jobDetail ? (
              <Stack spacing={1} alignItems="center" sx={{ py: 5, textAlign: 'center' }}>
                <FolderOpenRoundedIcon color="disabled" />
                <Typography variant="body1">No job selected</Typography>
                <Typography variant="body2" color="text.secondary">
                  Pick a job from the list to inspect generated files.
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
                    jobDetail.assets.map((asset) => (
                      <ListItem
                        key={asset.path}
                        divider={false}
                        secondaryAction={
                          <Stack direction="row" spacing={1}>
                            <Button
                              size="small"
                              startIcon={<VisibilityRoundedIcon />}
                              onClick={() => setPreviewAsset(asset)}
                              disabled={!asset.url}
                            >
                              Preview
                            </Button>
                            {asset.url ? (
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
                            ) : null}
                          </Stack>
                        }
                        sx={{
                          px: 1.5,
                          py: 1,
                          borderRadius: 2,
                          border: '1px solid',
                          borderColor: 'divider',
                        }}
                      >
                        <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ pr: 18 }}>
                          {renderAssetIcon(asset.relative)}
                          <ListItemText
                            primary={asset.relative}
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
        </CardContent>
      </Card>

      <Dialog open={Boolean(previewAsset)} onClose={() => setPreviewAsset(null)} maxWidth="lg" fullWidth>
        <DialogTitle>{previewAsset?.relative ?? 'Asset preview'}</DialogTitle>
        <DialogContent dividers>
          {previewAsset ? <AssetPreview asset={previewAsset} /> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewAsset(null)}>Close</Button>
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
