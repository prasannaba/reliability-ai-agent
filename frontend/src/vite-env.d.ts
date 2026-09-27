/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Web base URL for the FastAPI backend ('' = same-origin). */
  readonly VITE_BACKEND_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
