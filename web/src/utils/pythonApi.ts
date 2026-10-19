/**
 * Base URL of the python_data (Flask/vnstock) service as seen by the browser.
 *
 * Defaults to the same-origin "/python_api" path: nginx proxies it to Flask in
 * production and next.config.ts rewrites it in development, so no CORS or
 * hard-coded host is needed. NEXT_PUBLIC_API_BASE_URL_PYTHON overrides it.
 */
export const PYTHON_API_BASE_URL = (
    process.env.NEXT_PUBLIC_API_BASE_URL_PYTHON || "/python_api"
).replace(/\/+$/, "");

/** URL of a python_data route, e.g. pythonApiUrl("/stock/FPT"). */
export const pythonApiUrl = (path: string): string =>
    `${PYTHON_API_BASE_URL}/${path.replace(/^\/+/, "")}`;
