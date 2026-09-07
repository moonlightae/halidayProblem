import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

type PdfConfig = { pdfs?: Record<string, string> };

const configPath = resolve(process.cwd(), 'halliday.config.json');
const localConfig: PdfConfig = existsSync(configPath)
  ? JSON.parse(readFileSync(configPath, 'utf8'))
  : {};

function localPdfMiddleware(
  request: { url?: string; method?: string; headers: { range?: string } },
  response: {
    statusCode: number;
    setHeader(name: string, value: string | number): void;
    end(body?: string): void;
  },
  next: () => void,
) {
  const pathname = new URL(request.url ?? '/', 'http://localhost').pathname;
  const match = pathname.match(/^\/api\/pdf\/([12])$/);
  if (!match) {
    next();
    return;
  }

  const pdfPath = localConfig.pdfs?.[match[1]];
  if (!pdfPath || !existsSync(pdfPath)) {
    response.statusCode = 404;
    response.setHeader('Content-Type', 'application/json; charset=utf-8');
    response.end(JSON.stringify({ error: 'configured_pdf_not_found', book: match[1] }));
    return;
  }

  const stats = statSync(pdfPath);
  const range = request.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
  response.setHeader('Content-Type', 'application/pdf');
  response.setHeader('Accept-Ranges', 'bytes');
  response.setHeader('Cache-Control', 'private, no-store');
  response.setHeader('ETag', `W/\"${stats.size}-${stats.mtimeMs}\"`);

  if (range) {
    const start = Number(range[1]);
    const requestedEnd = range[2] ? Number(range[2]) : stats.size - 1;
    const end = Math.min(requestedEnd, stats.size - 1);
    if (start > end || start >= stats.size) {
      response.statusCode = 416;
      response.setHeader('Content-Range', `bytes */${stats.size}`);
      response.end();
      return;
    }
    response.statusCode = 206;
    response.setHeader('Content-Range', `bytes ${start}-${end}/${stats.size}`);
    response.setHeader('Content-Length', end - start + 1);
    if (request.method === 'HEAD') {
      response.end();
      return;
    }
    createReadStream(pdfPath, { start, end }).pipe(response as never);
    return;
  }

  response.statusCode = 200;
  response.setHeader('Content-Length', stats.size);
  if (request.method === 'HEAD') {
    response.end();
    return;
  }
  createReadStream(pdfPath).pipe(response as never);
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'halliday-local-pdfs',
      configureServer(server) {
        server.middlewares.use(localPdfMiddleware);
      },
      configurePreviewServer(server) {
        server.middlewares.use(localPdfMiddleware);
      },
    },
  ],
  build: {
    target: 'es2022',
  },
});
