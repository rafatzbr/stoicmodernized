import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import Inventory2RoundedIcon from '@mui/icons-material/Inventory2Rounded';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import type { Job } from '../types';

type Props = {
  jobs: Job[];
  selectedJobId: string;
  isLoading: boolean;
  error?: string | null;
  deletingJobId?: string | null;
  onSelect: (jobId: string) => void;
  onRefresh: () => void;
  onDeleteRequest: (job: Job) => void;
};

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

export function JobsList({
  jobs,
  selectedJobId,
  isLoading,
  error,
  deletingJobId,
  onSelect,
  onRefresh,
  onDeleteRequest,
}: Props) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
            <Box>
              <Typography variant="overline" color="secondary.main">
                Library
              </Typography>
              <Typography variant="h6">Jobs</Typography>
            </Box>
            <Button size="small" startIcon={<RefreshRoundedIcon />} onClick={onRefresh}>
              Refresh
            </Button>
          </Stack>

          {isLoading ? (
            <Stack alignItems="center" justifyContent="center" spacing={1} sx={{ py: 5 }}>
              <CircularProgress size={28} />
              <Typography variant="body2" color="text.secondary">
                Loading jobs…
              </Typography>
            </Stack>
          ) : error ? (
            <Box sx={{ py: 3 }}>
              <Typography color="error.main" variant="body2">
                {error}
              </Typography>
            </Box>
          ) : jobs.length === 0 ? (
            <Stack spacing={1} alignItems="center" sx={{ py: 5, textAlign: 'center' }}>
              <Inventory2RoundedIcon color="disabled" />
              <Typography variant="body1">No jobs yet</Typography>
              <Typography variant="body2" color="text.secondary">
                Start a full run or run research first to create a job.
              </Typography>
            </Stack>
          ) : (
            <List disablePadding sx={{ display: 'grid', gap: 1 }}>
              {jobs.map((job) => {
                const isSelected = job.job_id === selectedJobId;
                const isDeleting = deletingJobId === job.job_id;

                return (
                  <Stack
                    key={job.job_id}
                    direction="row"
                    spacing={1}
                    alignItems="stretch"
                    sx={{
                      border: '1px solid',
                      borderColor: isSelected ? 'secondary.main' : 'divider',
                      borderRadius: 2,
                      overflow: 'hidden',
                    }}
                  >
                    <ListItemButton
                      selected={isSelected}
                      onClick={() => onSelect(job.job_id)}
                      sx={{
                        alignItems: 'flex-start',
                        flex: 1,
                        borderRadius: 0,
                      }}
                    >
                      <ListItemText
                        primary={
                          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                              {job.topic}
                            </Typography>
                            <Chip label={job.status} size="small" color={job.status === 'completed' ? 'success' : 'default'} />
                          </Stack>
                        }
                        secondary={
                          <Stack spacing={0.5} sx={{ mt: 1 }}>
                            <Typography variant="caption" color="text.secondary">
                              {job.job_id}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Created {formatDate(job.created_at)}
                            </Typography>
                          </Stack>
                        }
                      />
                    </ListItemButton>
                    <Tooltip title="Delete job and all job files">
                      <span>
                        <IconButton
                          color="error"
                          onClick={() => onDeleteRequest(job)}
                          disabled={isDeleting}
                          sx={{
                            borderLeft: '1px solid',
                            borderColor: 'divider',
                            borderRadius: 0,
                            px: 1.5,
                          }}
                        >
                          {isDeleting ? <CircularProgress size={18} color="inherit" /> : <DeleteOutlineRoundedIcon />}
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                );
              })}
            </List>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
