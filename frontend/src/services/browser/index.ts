/** Browser service bundle: remote FastAPI over HTTP + Web APIs. */
import type { Services } from '../types';
import { setAppToken } from '../http';
import { createBrowserCapabilities } from './capabilities';
import { createHttpApi } from './httpApi';

export function browserServices(): Services {
  const baseUrl = import.meta.env.VITE_BACKEND_URL ?? '';
  // Optional write-auth for shared deployments (memory only, never storage).
  setAppToken(import.meta.env.VITE_APP_TOKEN ?? '');
  return {
    backend: createHttpApi({ baseUrl }),
    platform: createBrowserCapabilities(),
  };
}

export { setAppToken };
