import axios from 'axios';

export const api = axios.create({
  baseURL: '',  // relative — Vite proxy handles /api in dev, same-origin in prod
  timeout: 30000,
});

// ── News dashboard types ──────────────────────────────────────────────────

export interface NewsStory {
  title: string;
  url: string;
  source: string;
  relevance: number;
  summary: string | null;
  snippet: string | null;
  content: string | null;
  original_title: string | null;
}

export interface FetchNewsResponse {
  stories: NewsStory[];
  count: number;
  added_count?: number;
}

export interface SelectedNewsResponse {
  stories: NewsStory[];
  selected_count: number;
}
