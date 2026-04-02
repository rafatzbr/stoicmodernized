import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import FiberManualRecordRoundedIcon from '@mui/icons-material/FiberManualRecordRounded';
import StopCircleRoundedIcon from '@mui/icons-material/StopCircleRounded';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Grid,
  Paper,
  Snackbar,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material';
import { AxiosError } from 'axios';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  deleteJob,
  fetchConfigFile,
  fetchEnv,
  fetchJob,
  fetchJobs,
  fetchRun,
  saveConfigFile,
  saveEnv,
  startRun,
  startSteps,
  stopRun,
  suggestTopic,
} from '../api';
import { FileEditors } from '../components/FileEditors';
import { JobAssets } from '../components/JobAssets';
import { JobsList } from '../components/JobsList';
import { LiveLogs } from '../components/LiveLogs';
import { RunControls } from '../components/RunControls';
import { StepRunner } from '../components/StepRunner';
import type { Job, JobDetail, RunState } from '../types';

const DEFAULT_STEPS = ['research', 'script', 'scene', 'tts', 'images', 'subtitles', 'render', 'metadata'];

type Notice = {
  message: string;
  severity: 'success' | 'info' | 'warning' | 'error';
};

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') {
      return detail;
    }

    return error.message || fallback;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

export function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null);
  const [jobDetailLoading, setJobDetailLoading] = useState(false);
  const [topic, setTopic] = useState('workplace stress');
  const [videoMode, setVideoMode] = useState('short');
  const [provider, setProvider] = useState('edge');
  const [runId, setRunId] = useState<string | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [envContent, setEnvContent] = useState('');
  const [configContent, setConfigContent] = useState('');
  const [configLoading, setConfigLoading] = useState(true);
  const [selectedSteps, setSelectedSteps] = useState<string[]>(DEFAULT_STEPS);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pendingDeleteJob, setPendingDeleteJob] = useState<Job | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [suggestingTopic, setSuggestingTopic] = useState(false);

  const showNotice = useCallback((message: string, severity: Notice['severity'] = 'info') => {
    setNotice({ message, severity });
  }, []);

  const loadJobs = useCallback(async () => {
    setJobsLoading(true);
    setJobsError(null);

    try {
      const nextJobs = await fetchJobs();
      setJobs(nextJobs);
      if (selectedJobId && !nextJobs.some((job) => job.job_id === selectedJobId)) {
        setSelectedJobId('');
        setJobDetail(null);
      }
    } catch (error) {
      setJobsError(getErrorMessage(error, 'Failed to load jobs.'));
    } finally {
      setJobsLoading(false);
    }
  }, [selectedJobId]);

  const loadConfigFiles = useCallback(async () => {
    setConfigLoading(true);

    try {
      const [envResult, configResult] = await Promise.all([fetchEnv(), fetchConfigFile()]);
      setEnvContent(envResult.content);
      setConfigContent(configResult.content);
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to load config files.'), 'error');
    } finally {
      setConfigLoading(false);
    }
  }, [showNotice]);

  const loadJobDetail = useCallback(
    async (jobId: string) => {
      setJobDetailLoading(true);
      try {
        const detail = await fetchJob(jobId);
        setJobDetail(detail);
      } catch (error) {
        setJobDetail(null);
        showNotice(getErrorMessage(error, 'Failed to load job detail.'), 'error');
      } finally {
        setJobDetailLoading(false);
      }
    },
    [showNotice],
  );

  useEffect(() => {
    void Promise.all([loadJobs(), loadConfigFiles()]);
  }, [loadConfigFiles, loadJobs]);

  useEffect(() => {
    if (!runId) {
      return undefined;
    }

    let cancelled = false;

    const pollRun = async () => {
      try {
        const nextRunState = await fetchRun(runId);
        if (cancelled) {
          return;
        }

        setRunState(nextRunState);

        if (!nextRunState.running) {
          await loadJobs();
          if (selectedJobId) {
            await loadJobDetail(selectedJobId);
          }
        }
      } catch (error) {
        if (!cancelled) {
          showNotice(getErrorMessage(error, 'Failed to refresh run state.'), 'error');
        }
      }
    };

    void pollRun();
    const timer = window.setInterval(() => {
      void pollRun();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadJobDetail, loadJobs, runId, selectedJobId, showNotice]);

  const onStart = useCallback(async () => {
    setRunLoading(true);
    try {
      const result = await startRun({ topic, video_mode: videoMode, provider, skip_upload: true });
      setRunId(result.run_id);
      setRunState(null);
      showNotice(`Run started: ${result.run_id}`, 'success');
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to start run.'), 'error');
    } finally {
      setRunLoading(false);
    }
  }, [provider, showNotice, topic, videoMode]);

  const onSelectJob = useCallback(
    async (jobId: string) => {
      setSelectedJobId(jobId);
      await loadJobDetail(jobId);
    },
    [loadJobDetail],
  );

  const onSuggestTopic = useCallback(async () => {
    setSuggestingTopic(true);
    try {
      const result = await suggestTopic(topic);
      setTopic(result.topic);
      showNotice(
        result.source === 'local-ai' ? 'Suggested a topic using the local AI model.' : 'Local AI was unavailable, so I used a fallback topic.',
        result.source === 'local-ai' ? 'success' : 'warning',
      );
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to suggest a topic.'), 'error');
    } finally {
      setSuggestingTopic(false);
    }
  }, [showNotice, topic]);

  const onToggleStep = useCallback((step: string) => {
    setSelectedSteps((previous) =>
      previous.includes(step) ? previous.filter((item) => item !== step) : [...previous, step],
    );
  }, []);

  const onRunSteps = useCallback(async () => {
    setRunLoading(true);
    try {
      const result = await startSteps({
        topic,
        job_id: selectedJobId || null,
        video_mode: videoMode,
        provider,
        steps: selectedSteps,
      });
      setRunId(result.run_id);
      setRunState(null);
      showNotice(`Selected steps started: ${result.run_id}`, 'success');
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to start selected steps.'), 'error');
    } finally {
      setRunLoading(false);
    }
  }, [provider, selectedJobId, selectedSteps, showNotice, topic, videoMode]);

  const onStopRun = useCallback(async () => {
    if (!runId) {
      return;
    }

    try {
      await stopRun(runId);
      setRunState((previous) => (previous ? { ...previous, running: false } : previous));
      showNotice(`Stopped run: ${runId}`, 'warning');
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to stop run.'), 'error');
    }
  }, [runId, showNotice]);

  const onDeleteJob = useCallback(async () => {
    if (!pendingDeleteJob) {
      return;
    }

    const job = pendingDeleteJob;
    setDeletingJobId(job.job_id);

    try {
      await deleteJob(job.job_id);
      if (selectedJobId === job.job_id) {
        setSelectedJobId('');
        setJobDetail(null);
      }
      setPendingDeleteJob(null);
      await loadJobs();
      showNotice(`Deleted job: ${job.topic}`, 'success');
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to delete job.'), 'error');
    } finally {
      setDeletingJobId(null);
    }
  }, [loadJobs, pendingDeleteJob, selectedJobId, showNotice]);

  const summary = useMemo(
    () => [
      { label: 'Jobs', value: jobs.length.toString(), tone: 'default' as const },
      { label: 'Selected steps', value: selectedSteps.length.toString(), tone: 'secondary' as const },
      {
        label: 'Run status',
        value: runState?.running ? 'Running' : runId ? 'Idle' : 'Ready',
        tone: runState?.running ? ('warning' as const) : ('success' as const),
      },
      { label: 'Provider', value: provider, tone: 'default' as const },
    ],
    [jobs.length, provider, runId, runState?.running, selectedSteps.length],
  );

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" color="transparent" elevation={0} sx={{ backdropFilter: 'blur(18px)', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar sx={{ gap: 2, flexWrap: 'wrap', py: 1 }}>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flexGrow: 1 }}>
            <AutoAwesomeRoundedIcon color="secondary" />
            <Box>
              <Typography variant="h6">Stoic Modernized Control Panel</Typography>
              <Typography variant="body2" color="text.secondary">
                Internal dashboard for runs, assets, configs, and live pipeline control.
              </Typography>
            </Box>
          </Stack>

          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
            <Chip
              icon={<FiberManualRecordRoundedIcon sx={{ fontSize: 10 }} />}
              label={runState?.running ? `Active run ${runId}` : 'System ready'}
              color={runState?.running ? 'warning' : 'success'}
              variant="outlined"
            />
            <Button
              variant="outlined"
              color="warning"
              onClick={onStopRun}
              startIcon={<StopCircleRoundedIcon />}
              disabled={!runId || !runState?.running}
            >
              Stop run
            </Button>
          </Stack>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ py: { xs: 3, md: 4 } }}>
        <Stack spacing={3}>
          <Paper sx={{ p: { xs: 2, md: 3 }, backgroundImage: 'radial-gradient(circle at top right, rgba(203, 166, 247, 0.18), transparent 35%)' }}>
            <Stack spacing={2.5}>
              <Box>
                <Typography variant="overline" color="secondary.main">
                  Overview
                </Typography>
                <Typography variant="h4" sx={{ mb: 1 }}>
                  Pipeline command center
                </Typography>
                <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 900 }}>
                  Start full runs, execute individual stages, inspect job outputs, watch live logs, and tune configuration files from one place.
                </Typography>
              </Box>

              <Grid container spacing={2}>
                {summary.map((item) => (
                  <Grid key={item.label} size={{ xs: 6, md: 3 }}>
                    <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
                      <Typography variant="body2" color="text.secondary">
                        {item.label}
                      </Typography>
                      <Typography variant="h5" sx={{ mt: 1, mb: 1 }}>
                        {item.value}
                      </Typography>
                      <Chip size="small" label={item.tone === 'secondary' ? 'Configurable' : item.value} color={item.tone} variant="outlined" />
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </Stack>
          </Paper>

          <Grid container spacing={3}>
            <Grid size={{ xs: 12, lg: 4 }}>
              <Stack spacing={3}>
                <RunControls
                  topic={topic}
                  videoMode={videoMode}
                  provider={provider}
                  isStarting={runLoading}
                  isSuggestingTopic={suggestingTopic}
                  onTopicChange={setTopic}
                  onVideoModeChange={setVideoMode}
                  onProviderChange={setProvider}
                  onSuggestTopic={onSuggestTopic}
                  onStart={onStart}
                />
                <StepRunner
                  selectedJobId={selectedJobId}
                  selectedSteps={selectedSteps}
                  isRunning={runLoading}
                  onToggleStep={onToggleStep}
                  onRunSteps={onRunSteps}
                />
                <JobsList
                  jobs={jobs}
                  selectedJobId={selectedJobId}
                  isLoading={jobsLoading}
                  error={jobsError}
                  deletingJobId={deletingJobId}
                  onSelect={onSelectJob}
                  onRefresh={() => {
                    void loadJobs();
                  }}
                  onDeleteRequest={setPendingDeleteJob}
                />
              </Stack>
            </Grid>

            <Grid size={{ xs: 12, lg: 8 }}>
              <Stack spacing={3}>
                <LiveLogs runState={runState} onClear={() => setRunState(null)} />
                {jobDetailLoading ? (
                  <Paper variant="outlined" sx={{ p: 3 }}>
                    <Typography variant="body2" color="text.secondary">
                      Loading job details…
                    </Typography>
                  </Paper>
                ) : (
                  <JobAssets jobDetail={jobDetail} />
                )}
                <FileEditors
                  envContent={envContent}
                  configContent={configContent}
                  isLoading={configLoading}
                  onEnvChange={setEnvContent}
                  onConfigChange={setConfigContent}
                  onSaveEnv={async () => {
                    try {
                      await saveEnv(envContent);
                      showNotice('Saved .env', 'success');
                    } catch (error) {
                      showNotice(getErrorMessage(error, 'Failed to save .env'), 'error');
                    }
                  }}
                  onSaveConfig={async () => {
                    try {
                      await saveConfigFile(configContent);
                      showNotice('Saved src/config.py', 'success');
                    } catch (error) {
                      showNotice(getErrorMessage(error, 'Failed to save config.py'), 'error');
                    }
                  }}
                />
              </Stack>
            </Grid>
          </Grid>
        </Stack>
      </Container>

      <Dialog open={Boolean(pendingDeleteJob)} onClose={() => (deletingJobId ? undefined : setPendingDeleteJob(null))} maxWidth="xs" fullWidth>
        <DialogTitle>Delete job?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {pendingDeleteJob
              ? `This will permanently delete the job directory for “${pendingDeleteJob.topic}” and remove its database entry.`
              : 'This will permanently delete the selected job and its files.'}
          </DialogContentText>
          {pendingDeleteJob ? (
            <Stack spacing={0.75} sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Job ID: {pendingDeleteJob.job_id}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                This cannot be undone.
              </Typography>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingDeleteJob(null)} disabled={Boolean(deletingJobId)}>
            Cancel
          </Button>
          <Button color="error" variant="contained" onClick={() => void onDeleteJob()} disabled={Boolean(deletingJobId)}>
            {deletingJobId ? 'Deleting…' : 'Delete job'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={Boolean(notice)} autoHideDuration={3500} onClose={() => setNotice(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
        <Alert onClose={() => setNotice(null)} severity={notice?.severity ?? 'info'} variant="filled" sx={{ width: '100%' }}>
          {notice?.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
