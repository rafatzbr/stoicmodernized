import axios from 'axios';

function resolveBaseUrl() {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();

  if (configured) {
    return configured;
  }

  if (typeof window === 'undefined') {
    return 'http://localhost:8000';
  }

  const { hostname, origin, port } = window.location;

  if (port === '5173' || port === '4173') {
    return `http://${hostname || 'localhost'}:8000`;
  }

  return origin;
}

export const api = axios.create({
  baseURL: resolveBaseUrl(),
  timeout: 30000,
});
