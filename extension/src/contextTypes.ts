import type { useApi } from './api';

// make sure api is called when rendering...
export type Api = ReturnType<typeof useApi>;

// response after confirming soemthing can be uploaded
export type UploadUrlResponse = {
  filename: string;
  path: string | null;
  signed_url: string | null;
  error: string | null;
};

// to be sent to backend table
export type ContextCreate = {
  type: 'file';
  file_link: string;
  metadata?: Record<string, unknown>;
};

// the context is either created... or it is rejected
export type UploadOutcome =
  | { context: ContextCreate[] }
  | { rejected: { index: number; error: string }[] };
