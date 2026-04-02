import ArticleRoundedIcon from '@mui/icons-material/ArticleRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import FolderOpenRoundedIcon from '@mui/icons-material/FolderOpenRounded';
import MovieRoundedIcon from '@mui/icons-material/MovieRounded';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Link,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import type { JobDetail } from '../types';

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

export function JobAssets({ jobDetail }: { jobDetail: JobDetail | null }) {
  return (
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
                        ) : undefined
                      }
                      sx={{
                        px: 1.5,
                        py: 1,
                        borderRadius: 2,
                        border: '1px solid',
                        borderColor: 'divider',
                      }}
                    >
                      <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ pr: 8 }}>
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
  );
}
