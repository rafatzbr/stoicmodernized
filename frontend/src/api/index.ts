import { api } from './client';
import type { Job, JobDetail, RunState } from '../types';

export async function fetchJobs() {
  const res = await api.get<Job[]>('/api/jobs');
  return res.data;
}

export async function fetchJob(jobId: string) {
  const res = await api.get<JobDetail>(`/api/jobs/${jobId}`);
  return res.data;
}

export async function startRun(payload: {
  topic: string;
  video_mode: string;
  provider: string;
  skip_upload: boolean;
}) {
  const res = await api.post<{ run_id: string }>('/api/runs', payload);
  return res.data;
}

export async function startSteps(payload: {
  topic: string;
  job_id?: string | null;
  video_mode: string;
  provider: string;
  steps: string[];
}) {
  const res = await api.post<{ run_id: string; job_id?: string | null }>('/api/runs/steps', payload);
  return res.data;
}

export async function fetchRun(runId: string) {
  const res = await api.get<RunState>(`/api/runs/${runId}`);
  return res.data;
}

export async function stopRun(runId: string) {
  return api.post(`/api/runs/${runId}/stop`);
}

export async function fetchEnv() {
  const res = await api.get<{ content: string }>('/api/config/env');
  return res.data;
}

export async function saveEnv(content: string) {
  return api.post('/api/config/env', { content });
}

export async function fetchConfigFile() {
  const res = await api.get<{ content: string }>('/api/config/file');
  return res.data;
}

export async function saveConfigFile(content: string) {
  return api.post('/api/config/file', { content });
}


export async function deleteJob(jobId: string) {
  const res = await api.delete<{ deleted: boolean; job_id: string; removed_dir: boolean; removed_db: boolean }>(`/api/jobs/${jobId}`);
  return res.data;
}
