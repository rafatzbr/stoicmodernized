import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
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

function toneForStatus(status: string) {
  if (status.includes('fail')) return 'error.main';
  if (status.includes('complete')) return 'success.main';
  if (status.includes('run')) return 'warning.main';
  return 'text.secondary';
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
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-end" spacing={2}>
        <Box>
          <Typography variant="overline" color="text.secondary">
            JOBS
          </Typography>
          <Typography variant="h5">Recent runs</Typography>
        </Box>
        <Button variant="outlined" size="small" startIcon={<RefreshRoundedIcon />} onClick={onRefresh}>
          REFRESH
        </Button>
      </Stack>

      {isLoading ? (
        <Stack alignItems="center" spacing={1.5} sx={{ py: 6 }}>
          <CircularProgress size={24} />
          <Typography variant="body2" color="text.secondary">
            Loading jobs…
          </Typography>
        </Stack>
      ) : error ? (
        <Typography color="error.main" variant="body2">
          {error}
        </Typography>
      ) : jobs.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No jobs yet. Start a run to populate this list.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {jobs.map((job) => {
            const isSelected = job.job_id === selectedJobId;
            const isDeleting = deletingJobId === job.job_id;

            return (
              <Stack
                key={job.job_id}
                direction="row"
                sx={{
                  border: '1px solid',
                  borderColor: isSelected ? 'primary.main' : 'divider',
                  backgroundColor: isSelected ? 'rgba(255,255,255,0.04)' : 'transparent',
                }}
              >
                <Box
                  onClick={() => onSelect(job.job_id)}
                  sx={{
                    flex: 1,
                    px: 2,
                    py: 1.5,
                    cursor: 'pointer',
                    borderLeft: '2px solid',
                    borderLeftColor: isSelected ? 'primary.main' : 'transparent',
                  }}
                >
                  <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="flex-start">
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {job.topic}
                    </Typography>
                    <Typography variant="caption" color={toneForStatus(job.status)}>
                      {job.status.toUpperCase()}
                    </Typography>
                  </Stack>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                    {(job.channel_name ?? job.channel ?? 'channel').toUpperCase()} · {formatDate(job.created_at)}
                  </Typography>
                  <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 0.25 }}>
                    {job.job_id}
                  </Typography>
                </Box>
                <Tooltip title="Delete job and files">
                  <span>
                    <IconButton
                      color="error"
                      onClick={() => onDeleteRequest(job)}
                      disabled={isDeleting}
                      sx={{ borderLeft: '1px solid', borderColor: 'divider', borderRadius: 0, px: 1.5 }}
                    >
                      {isDeleting ? <CircularProgress size={16} color="inherit" /> : <DeleteOutlineRoundedIcon />}
                    </IconButton>
                  </span>
                </Tooltip>
              </Stack>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}
