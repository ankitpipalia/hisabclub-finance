import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});

// Default API URL used by client.ts during tests so it doesn't try to hit a
// real backend. Tests that exercise the network path should mock fetch.
process.env.VITE_API_URL = 'http://test.local/api/v1';

// react-pdf relies on a PDF.js worker that jsdom can't load — stub it so
// any module that pulls in <Document /> doesn't crash the test runner.
class StubWorker {
  postMessage() {}
  terminate() {}
  addEventListener() {}
  removeEventListener() {}
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: ErrorEvent) => void) | null = null;
}
(globalThis as unknown as { Worker: typeof StubWorker }).Worker = StubWorker;
