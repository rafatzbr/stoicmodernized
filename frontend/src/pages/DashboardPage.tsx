import StopCircleRoundedIcon from '@mui/icons-material/StopCircleRounded';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Paper,
  Snackbar,
  Stack,
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
  uploadJobAsset,
} from '../api';
import { FileEditors } from '../components/FileEditors';
import { JobAssets } from '../components/JobAssets';
import { JobsList } from '../components/JobsList';
import { LiveLogs } from '../components/LiveLogs';
import { RunControls } from '../components/RunControls';
import type { Job, JobDetail, RunState } from '../types';

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

function extractEnvValue(content: string, key: string): string | null {
  const line = content
    .split('\n')
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${key}=`) && !item.startsWith('#'));

  if (!line) {
    return null;
  }

  const raw = line.slice(key.length + 1).trim();
  return raw.replace(/^['"]|['"]$/g, '');
}

function resolveHeroStatus(runState: RunState | null, runId: string | null) {
  if (runState?.running) return 'RUNNING';
  if (runState && runState.returncode === 0) return 'COMPLETE';
  if (runState && runState.returncode !== null && runState.returncode !== 0) return 'FAILED';
  if (runId) return 'IDLE';
  return 'READY';
}

export function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null);
  const [channel, setChannel] = useState('stoic-modernized');
  const [renderer, setRenderer] = useState('remotion');
  const [jobDetailLoading, setJobDetailLoading] = useState(false);
  const [topic, setTopic] = useState('workplace stress');
  const [videoMode, setVideoMode] = useState('short');
  const [platform, setPlatform] = useState('auto');
  const [provider, setProvider] = useState('voxcpm');
  const [runId, setRunId] = useState<string | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [envContent, setEnvContent] = useState('');
  const [configContent, setConfigContent] = useState('');
  const [configLoading, setConfigLoading] = useState(true);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pendingDeleteJob, setPendingDeleteJob] = useState<Job | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [suggestingTopic, setSuggestingTopic] = useState(false);

  const showNotice = useCallback((message: string, severity: Notice['severity'] = 'info') => {
    setNotice({ message, severity });
  }, []);

  const onChannelChange = useCallback((nextChannel: string) => {
    setChannel(nextChannel);
    if (nextChannel === 'ai-signal') {
      setRenderer('remotion');
    }
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

      const envProvider = extractEnvValue(envResult.content, 'TTS_PROVIDER');
      if (envProvider) {
        setProvider(envProvider);
      }
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
        if (detail.channel) {
          setChannel(detail.channel);
        }
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
          if (!cancelled) {
            setRunId(null);
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

  const effectiveTopic = channel === 'ai-signal' ? 'AI news' : topic;

  const onStart = useCallback(async () => {
    setRunLoading(true);
    try {
      const result = await startRun({
        topic: effectiveTopic,
        video_mode: videoMode,
        provider,
        channel,
        platform: platform === 'auto' ? null : platform,
        skip_upload: true,
        renderer,
      });
      setRunId(result.run_id);
      setRunState(null);
      showNotice(`Run started: ${result.run_id}`, 'success');
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to start run.'), 'error');
    } finally {
      setRunLoading(false);
    }
  }, [channel, effectiveTopic, platform, provider, renderer, showNotice, videoMode]);

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
      const result = await suggestTopic(effectiveTopic, channel);
      if (result.source !== 'local-ai' || !result.topic) {
        showNotice(result.error || 'Local topic suggestion failed.', 'error');
        return;
      }
      setTopic(result.topic);
      showNotice('Suggested a topic using the local AI model.', 'success');
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to suggest a topic.'), 'error');
    } finally {
      setSuggestingTopic(false);
    }
  }, [channel, effectiveTopic, showNotice]);

  const onRunSpecificSteps = useCallback(
    async (steps: string[], rendererOverride?: string) => {
      if (!steps.length) {
        return;
      }

      const nextRenderer = rendererOverride ?? renderer;

      setRunLoading(true);
      try {
        const result = await startSteps({
          topic: effectiveTopic,
          job_id: selectedJobId || null,
          video_mode: videoMode,
          provider,
          channel,
          platform: platform === 'auto' ? null : platform,
          steps,
          renderer: nextRenderer,
        });
        setRunId(result.run_id);
        setRunState(null);
        showNotice(`Rerun started: ${result.run_id}`, 'success');
      } catch (error) {
        showNotice(getErrorMessage(error, 'Failed to rerun selected steps.'), 'error');
      } finally {
        setRunLoading(false);
      }
    },
    [channel, effectiveTopic, platform, provider, renderer, selectedJobId, showNotice, videoMode],
  );

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

  const onFullRerun = useCallback(async () => {
    if (!jobDetail) {
      return;
    }

    setRunLoading(true);
    try {
      const result = await startRun({
        topic: jobDetail.topic,
        video_mode: videoMode,
        provider,
        channel: jobDetail.channel ?? channel,
        platform: platform === 'auto' ? null : platform,
        skip_upload: true,
        renderer,
      });
      setRunId(result.run_id);
      setRunState(null);
      showNotice(`Full rerun started: ${result.run_id}`, 'success');
    } catch (error) {
      showNotice(getErrorMessage(error, 'Failed to start full rerun.'), 'error');
    } finally {
      setRunLoading(false);
    }
  }, [channel, jobDetail, platform, provider, renderer, showNotice, videoMode]);

  const onUploadAsset = useCallback(
    async (assetPath: string) => {
      if (!jobDetail) {
        return;
      }

      setRunLoading(true);
      try {
        const result = await uploadJobAsset(jobDetail.job_id, { asset_path: assetPath });
        setRunId(result.run_id);
        setRunState(null);
        showNotice(`Upload started: ${assetPath}`, 'success');
      } catch (error) {
        showNotice(getErrorMessage(error, 'Failed to start upload.'), 'error');
      } finally {
        setRunLoading(false);
      }
    },
    [jobDetail, showNotice],
  );

  const heroStatus = resolveHeroStatus(runState, runId);
  const summary = useMemo(
    () => [
      { label: 'CHANNEL', value: channel === 'ai-signal' ? 'AI SIGNAL' : 'STOIC' },
      { label: 'JOBS', value: String(jobs.length).padStart(2, '0') },
      { label: 'RENDERER', value: renderer.toUpperCase() },
    ],
    [channel, jobs.length, renderer],
  );

  return (
    <Box sx={{ minHeight: '100vh', px: { xs: 2, md: 4 }, py: { xs: 2, md: 3 } }}>
      <Stack spacing={2}>
        <Paper sx={{ p: { xs: 2.25, md: 3 }, border: '1px solid', borderColor: 'divider' }}>
          <Stack spacing={3}>
            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={3}>
              <Stack spacing={1}>
                <Typography variant="overline" color="text.secondary">
                  STOIC MODERNIZED CONTROL SURFACE
                </Typography>
                <Typography sx={{ fontSize: { xs: 48, md: 84 }, lineHeight: 0.95, letterSpacing: '-0.06em', fontWeight: 500 }}>
                  {heroStatus}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 760 }}>
                  One surface for starting runs, rerunning slices, checking artifacts, and fixing configuration without digging through the repo.
                </Typography>
              </Stack>

              <Stack spacing={1.25} alignItems={{ xs: 'flex-start', md: 'flex-end' }}>
                <Typography variant="overline" color="text.secondary">
                  ACTIVE RUN
                </Typography>
                <Typography variant="body2">{runId ?? 'NONE'}</Typography>
                <Button
                  variant="outlined"
                  color="error"
                  onClick={onStopRun}
                  startIcon={<StopCircleRoundedIcon />}
                  disabled={!runId || !runState?.running}
                >
                  STOP RUN
                </Button>
              </Stack>
            </Stack>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
              {summary.map((item) => (
                <Box key={item.label} sx={{ minWidth: 132, borderTop: '1px solid', borderColor: 'divider', pt: 1 }}>
                  <Typography variant="overline" color="text.secondary">
                    {item.label}
                  </Typography>
                  <Typography variant="h6">{item.value}</Typography>
                </Box>
              ))}
            </Stack>
          </Stack>
        </Paper>

        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: '1fr', xl: '380px minmax(0, 1fr)' },
            alignItems: 'start',
          }}
        >
          <Stack spacing={2}>
            <Paper sx={{ p: 3 }}>
              <RunControls
                topic={topic}
                channel={channel}
                videoMode={videoMode}
                provider={provider}
                platform={platform}
                renderer={renderer}
                isStarting={runLoading}
                isSuggestingTopic={suggestingTopic}
                onTopicChange={setTopic}
                onChannelChange={onChannelChange}
                onVideoModeChange={setVideoMode}
                onProviderChange={setProvider}
                onPlatformChange={setPlatform}
                onRendererChange={setRenderer}
                onSuggestTopic={onSuggestTopic}
                onStart={onStart}
              />
            </Paper>

            <Paper sx={{ p: 3 }}>
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
            </Paper>
          </Stack>

          <Stack spacing={2}>
            <Paper sx={{ p: 3 }}>
              <LiveLogs runState={runState} onClear={() => setRunState(null)} />
            </Paper>

            <Paper sx={{ p: 3 }}>
              {jobDetailLoading ? (
                <Typography variant="body2" color="text.secondary">
                  Loading job details…
                </Typography>
              ) : (
                <JobAssets
                  jobDetail={jobDetail}
                  onRefresh={() => {
                    if (selectedJobId) {
                      void loadJobDetail(selectedJobId);
                    }
                  }}
                  onRerunSteps={(steps, rendererOverride) => {
                    void onRunSpecificSteps(steps, rendererOverride);
                  }}
                  onFullRerun={onFullRerun}
                  onUploadAsset={(assetPath) => {
                    void onUploadAsset(assetPath);
                  }}
                  rerunBusy={runLoading || Boolean(runId && runState?.running)}
                />
              )}
            </Paper>

            <Paper sx={{ p: 3 }}>
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
            </Paper>
          </Stack>
        </Box>
      </Stack>

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
