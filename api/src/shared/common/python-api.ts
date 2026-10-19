const DEFAULT_PYTHON_API_URL = 'http://python_data:6060/api';

/** Base URL of the python_data (Flask/vnstock) service, without trailing slash. */
export const pythonApiBaseUrl = (): string =>
  (
    process.env.PYTHON_API_URL?.trim() ||
    process.env.PYTHON_API?.trim() ||
    DEFAULT_PYTHON_API_URL
  ).replace(/\/+$/, '');

/** Absolute URL of a python_data route, e.g. pythonApiUrl('/stock/FPT'). */
export const pythonApiUrl = (path: string): string =>
  `${pythonApiBaseUrl()}/${path.replace(/^\/+/, '')}`;
