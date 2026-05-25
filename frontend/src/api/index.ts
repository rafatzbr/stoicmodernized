import type { Job, JobDetail, RunState } from '../types';
import type { FetchNewsResponse, SelectedNewsResponse } from './client';
import { api } from './client';

export type TopicSuggestionResult = {
  topic: string;
  source: string;
  error?: string;
  thinking?: string;
  used_reasoning_fallback?: boolean;
  finish_reason?: string | null;
  raw_content?: string;
};

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
  channel?: string;
  platform?: string | null;
  skip_upload: boolean;
  renderer?: string;
}) {
  const res = await api.post<{ run_id: string }>('/api/runs', payload);
  return res.data;
}

export async function startSteps(payload: {
  topic: string;
  job_id?: string | null;
  video_mode: string;
  provider: string;
  channel?: string;
  platform?: string | null;
  steps: string[];
  renderer?: string;
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

export async function deleteJob(jobId: string) {
  const res = await api.delete<{ deleted: boolean; job_id: string; removed_dir: boolean; removed_db: boolean }>(`/api/jobs/${jobId}`);
  return res.data;
}

export async function uploadJobAsset(jobId: string, payload: { asset_path: string; mock?: boolean }) {
  const res = await api.post<{ run_id: string }>(`/api/jobs/${jobId}/upload`, payload);
  return res.data;
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

export async function suggestTopic(current_topic?: string, channel?: string) {
  const res = await api.post<TopicSuggestionResult>('/api/topics/suggest', { current_topic, channel });
  return res.data;
}

// ── News dashboard ────────────────────────────────────────────────────────

export async function fetchNews(channel: string, append = false): Promise<FetchNewsResponse> {
  const res = await api.post<FetchNewsResponse>('/api/news/fetch', null, { params: { channel, append } });
  return res.data;
}

export async function saveSelectedNews(channel: string, indices: number[]): Promise<{ selected_count: number }> {
  const res = await api.post<{ selected_count: number }>('/api/news/selected', { indices }, { params: { channel } });
  return res.data;
}

export async function getSelectedNews(channel: string): Promise<SelectedNewsResponse> {
  const res = await api.get<SelectedNewsResponse>('/api/news/selected', { params: { channel } });
  return res.data;
}

export async function clearSelectedNews(channel: string): Promise<{ cleared: string }> {
  const res = await api.delete<{ cleared: string }>('/api/news/selected', { params: { channel } });
  return res.data;
}

export async function generateFromSelectedNews(payload: {
  channel: string;
  topic: string;
  video_mode: string;
  provider: string;
  renderer: string;
  skip_upload?: boolean;
  platform?: string | null;
}): Promise<{ run_id: string; job_id?: string }> {
  const res = await api.post<{ run_id: string; job_id?: string }>('/api/news/generate', payload);
  return res.data;
}
