import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Atom,
  BookOpen,
  Check,
  CircleAlert,
  HardDrive,
  LoaderCircle,
  Minus,
  Plus,
  Search,
  Upload,
  X,
} from 'lucide-react';
import {
  GlobalWorkerOptions,
  getDocument,
  type PDFDocumentProxy,
  type RenderTask,
} from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import {
  getStoredFileHandle,
  storeFileHandle,
  supportsPersistentFileHandles,
} from './fileHandleStore';
import type { BookId, CropSegment, ProblemIndex } from './types';

GlobalWorkerOptions.workerSrc = pdfWorker;

interface LoadedBook {
  document: PDFDocumentProxy;
  fileName: string;
}

interface Selection {
  chapter: number;
  problem: number;
}

type ConnectionState = 'idle' | 'loading' | 'ready' | 'error';

const supportsLocalPdfBridge = import.meta.env.DEV;

const getBookId = (chapter: number): BookId => (chapter <= 20 ? '1' : '2');

const PHYSICAL_CONSTANTS = [
  { name: '진공에서의 빛의 속력', symbol: 'c', value: '2.997 924 58 × 10⁸', unit: 'm·s⁻¹' },
  { name: '중력 상수', symbol: 'G', value: '6.674 30 × 10⁻¹¹', unit: 'm³·kg⁻¹·s⁻²' },
  { name: '표준 중력 가속도', symbol: 'g₀', value: '9.806 65', unit: 'm·s⁻²' },
  { name: '기본 전하량', symbol: 'e', value: '1.602 176 634 × 10⁻¹⁹', unit: 'C' },
  { name: '전자 질량', symbol: 'mₑ', value: '9.109 383 7139 × 10⁻³¹', unit: 'kg' },
  { name: '양성자 질량', symbol: 'mₚ', value: '1.672 621 925 95 × 10⁻²⁷', unit: 'kg' },
  { name: '중성자 질량', symbol: 'mₙ', value: '1.674 927 500 56 × 10⁻²⁷', unit: 'kg' },
  { name: '진공 유전율', symbol: 'ε₀', value: '8.854 187 8188 × 10⁻¹²', unit: 'F·m⁻¹' },
  { name: '진공 투자율', symbol: 'μ₀', value: '1.256 637 061 27 × 10⁻⁶', unit: 'N·A⁻²' },
  { name: '쿨롱 상수', symbol: 'kₑ', value: '8.987 551 7862 × 10⁹', unit: 'N·m²·C⁻²' },
  { name: '플랑크 상수', symbol: 'h', value: '6.626 070 15 × 10⁻³⁴', unit: 'J·s' },
  { name: '환산 플랑크 상수', symbol: 'ℏ', value: '1.054 571 817… × 10⁻³⁴', unit: 'J·s' },
  { name: '볼츠만 상수', symbol: 'k_B', value: '1.380 649 × 10⁻²³', unit: 'J·K⁻¹' },
  { name: '아보가드로 상수', symbol: 'N_A', value: '6.022 140 76 × 10²³', unit: 'mol⁻¹' },
  { name: '기체 상수', symbol: 'R', value: '8.314 462 618…', unit: 'J·mol⁻¹·K⁻¹' },
  { name: '원자 질량 상수', symbol: 'u', value: '1.660 539 068 92 × 10⁻²⁷', unit: 'kg' },
  { name: '전자볼트', symbol: 'eV', value: '1.602 176 634 × 10⁻¹⁹', unit: 'J' },
  { name: '패러데이 상수', symbol: 'F', value: '96 485.332 12…', unit: 'C·mol⁻¹' },
  { name: 'Stefan-Boltzmann 상수', symbol: 'σ', value: '5.670 374 419… × 10⁻⁸', unit: 'W·m⁻²·K⁻⁴' },
] as const;

function ProblemCanvas({
  document,
  segment,
  zoom,
  index,
  label,
  loadingLabel = '문제를 선명하게 불러오는 중',
}: {
  document: PDFDocumentProxy;
  segment: CropSegment;
  zoom: number;
  index: number;
  label?: string;
  loadingLabel?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    let renderTask: RenderTask | null = null;

    async function render() {
      setStatus('loading');
      try {
        const page = await document.getPage(segment.page);
        if (cancelled) return;
        const scale = 3.15 * zoom;
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        if (!canvas) return;
        const context = canvas.getContext('2d', { alpha: false });
        if (!context) throw new Error('Canvas context is unavailable');

        canvas.width = Math.max(1, Math.round(viewport.width * segment.width));
        canvas.height = Math.max(1, Math.round(viewport.height * segment.height));
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, canvas.width, canvas.height);
        renderTask = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: [
            1,
            0,
            0,
            1,
            -viewport.width * segment.x,
            -viewport.height * segment.y,
          ],
        });
        await renderTask.promise;
        if (!cancelled) setStatus('ready');
      } catch (error) {
        if (!cancelled && (error as Error).name !== 'RenderingCancelledException') {
          setStatus('error');
        }
      }
    }

    void render();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [document, segment, zoom]);

  return (
    <div className={`problem-segment ${status}`}>
      {index > 0 && (
        <div className="segment-divider" aria-hidden="true">
          <span>이어지는 부분</span>
        </div>
      )}
      {status === 'loading' && (
        <div className="segment-loading" role="status">
          <LoaderCircle size={18} /> {loadingLabel}
        </div>
      )}
      {status === 'error' && (
        <div className="segment-error">이 부분을 렌더링하지 못했습니다.</div>
      )}
      <canvas ref={canvasRef} aria-label={label ?? `문제 이미지 ${index + 1}`} />
    </div>
  );
}

function App() {
  const [catalog, setCatalog] = useState<ProblemIndex | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const [chapterInput, setChapterInput] = useState('2');
  const [problemInput, setProblemInput] = useState('1');
  const [selection, setSelection] = useState<Selection>({ chapter: 2, problem: 1 });
  const [loadedBooks, setLoadedBooks] = useState<Partial<Record<BookId, LoadedBook>>>({});
  const [connectionState, setConnectionState] = useState<Record<BookId, ConnectionState>>({
    '1': supportsLocalPdfBridge ? 'loading' : 'idle',
    '2': supportsLocalPdfBridge ? 'loading' : 'idle',
  });
  const [message, setMessage] = useState(
    supportsLocalPdfBridge
      ? '등록된 교재 PDF를 자동으로 연결하고 있습니다.'
      : '사용할 교재 PDF 두 권을 선택해 주세요.',
  );
  const [zoom, setZoom] = useState(1);
  const [showChapterReview, setShowChapterReview] = useState(false);
  const [showPhysicalConstants, setShowPhysicalConstants] = useState(false);
  const autoConnectStarted = useRef(false);
  const persistentRestoreStarted = useRef(false);
  const objectUrls = useRef<Partial<Record<BookId, string>>>({});
  const uploadInputs = useRef<Partial<Record<BookId, HTMLInputElement>>>({});
  const reviewCloseRef = useRef<HTMLButtonElement>(null);
  const constantsCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    fetch('/problem-index.json?v=6', { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error('Index load failed');
        return response.json() as Promise<ProblemIndex>;
      })
      .then(setCatalog)
      .catch(() => setCatalogError(true));
  }, []);

  useEffect(() => {
    if (!supportsLocalPdfBridge || !catalog || autoConnectStarted.current) return;
    autoConnectStarted.current = true;

    async function connectAll() {
      const results = await Promise.allSettled(
        (['1', '2'] as BookId[]).map(async (bookId) => {
          const document = await getDocument({
            url: `/api/pdf/${bookId}`,
            rangeChunkSize: 1024 * 1024,
          }).promise;
          const expectedPages = catalog!.books[bookId].pageCount;
          if (document.numPages !== expectedPages) {
            await document.destroy();
            throw new Error(`${catalog!.books[bookId].label} 페이지 수가 일치하지 않습니다.`);
          }
          setLoadedBooks((current) => ({
            ...current,
            [bookId]: {
              document,
              fileName: catalog!.books[bookId].fileHint,
            },
          }));
          setConnectionState((current) => ({ ...current, [bookId]: 'ready' }));
        }),
      );

      const failedBooks = results
        .map((result, index) => (result.status === 'rejected' ? (String(index + 1) as BookId) : null))
        .filter((bookId): bookId is BookId => bookId !== null);
      if (failedBooks.length) {
        setConnectionState((current) => {
          const next = { ...current };
          failedBooks.forEach((bookId) => {
            next[bookId] = 'error';
          });
          return next;
        });
        setMessage('자동 연결하지 못한 교재는 아래에서 직접 선택해 주세요.');
      } else {
        setMessage('교재 PDF 두 권이 자동으로 연결되었습니다.');
      }
    }

    void connectAll();
  }, [catalog]);

  useEffect(() => {
    if (
      supportsLocalPdfBridge ||
      !catalog ||
      persistentRestoreStarted.current ||
      !supportsPersistentFileHandles()
    ) {
      return;
    }
    persistentRestoreStarted.current = true;

    async function restoreRememberedBooks() {
      let restoredCount = 0;
      let permissionCount = 0;
      await Promise.all(
        (['1', '2'] as BookId[]).map(async (bookId) => {
          try {
            const handle = await getStoredFileHandle(bookId);
            if (!handle) return;
            const permission = await handle.queryPermission({ mode: 'read' });
            if (permission !== 'granted') {
              permissionCount += 1;
              return;
            }
            setConnectionState((current) => ({ ...current, [bookId]: 'loading' }));
            if (await loadPdfFile(bookId, await handle.getFile())) restoredCount += 1;
          } catch {
            setConnectionState((current) => ({ ...current, [bookId]: 'error' }));
          }
        }),
      );

      if (restoredCount === 2) {
        setMessage('이 기기에 기억된 교재 PDF 두 권을 자동으로 연결했습니다.');
      } else if (restoredCount === 1) {
        setMessage('기억된 교재 한 권을 연결했습니다. 나머지 교재를 선택해 주세요.');
      } else if (permissionCount > 0) {
        setMessage('기억된 교재를 다시 연결하려면 해당 VOL. 버튼을 눌러 권한을 허용해 주세요.');
      }
    }

    void restoreRememberedBooks();
  }, [catalog]);

  useEffect(
    () => () => {
      Object.values(objectUrls.current).forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );

  const activeBookId = getBookId(selection.chapter);
  const activeBook = catalog?.books[activeBookId];
  const activeChapter = activeBook?.chapters[String(selection.chapter)];
  const activeProblem = activeChapter?.problems[String(selection.problem)];
  const activePdf = loadedBooks[activeBookId]?.document;
  const chapterInputNumber = Number(chapterInput);
  const problemInputNumber = Number(problemInput);
  const draftChapter =
    chapterInput !== '' && chapterInputNumber >= 1 && chapterInputNumber <= 44
      ? catalog?.books[getBookId(chapterInputNumber)].chapters[String(chapterInputNumber)]
      : undefined;

  useEffect(() => {
    const context = document.modelContext;
    if (!catalog || !context?.registerTool) return;
    const lifecycle = new AbortController();

    void Promise.resolve(
      context.registerTool(
        {
          name: 'show_halliday_problem',
          title: '할리데이 연습문제 보기',
          description: '할리데이 일반물리학 11판의 단원과 문제 번호를 선택해 화면에 표시합니다.',
          inputSchema: {
            type: 'object',
            properties: {
              chapter: { type: 'integer', minimum: 1, maximum: 44 },
              problem: { type: 'integer', minimum: 1 },
            },
            required: ['chapter', 'problem'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          execute(input) {
            if (!input || typeof input !== 'object') throw new Error('단원과 문제 번호가 필요합니다.');
            const { chapter, problem } = input as { chapter?: unknown; problem?: unknown };
            if (!Number.isInteger(chapter) || !Number.isInteger(problem)) {
              throw new Error('단원과 문제 번호는 정수여야 합니다.');
            }
            const chapterNumber = chapter as number;
            const problemNumber = problem as number;
            const bookId = getBookId(chapterNumber);
            const chapterEntry = catalog.books[bookId].chapters[String(chapterNumber)];
            if (!chapterEntry) throw new Error('1단원부터 44단원까지 선택할 수 있습니다.');
            if (problemNumber < 1 || problemNumber > chapterEntry.problemCount) {
              throw new Error(`${chapterNumber}단원은 1번부터 ${chapterEntry.problemCount}번까지 있습니다.`);
            }
            setChapterInput(String(chapterNumber));
            setProblemInput(String(problemNumber));
            setSelection({ chapter: chapterNumber, problem: problemNumber });
            setZoom(1);
            setMessage(`${chapterNumber}단원 ${problemNumber}번을 찾았습니다.`);
            return {
              chapter: chapterNumber,
              problem: problemNumber,
              title: chapterEntry.title,
              pdfConnected: Boolean(loadedBooks[bookId]),
            };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);

    return () => lifecycle.abort();
  }, [catalog, loadedBooks]);

  useEffect(() => {
    setShowChapterReview(false);
  }, [selection.chapter]);

  useEffect(() => {
    if (!showChapterReview && !showPhysicalConstants) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowChapterReview(false);
        setShowPhysicalConstants(false);
      }
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', closeOnEscape);
    (showChapterReview ? reviewCloseRef : constantsCloseRef).current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
      previousFocus?.focus();
    };
  }, [showChapterReview, showPhysicalConstants]);

  async function loadPdfFile(
    bookId: BookId,
    file: File,
    persistentHandle?: FileSystemFileHandle,
  ) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setConnectionState((current) => ({ ...current, [bookId]: 'error' }));
      setMessage('PDF 형식의 교재 파일을 선택해 주세요.');
      return false;
    }

    setConnectionState((current) => ({ ...current, [bookId]: 'loading' }));
    setMessage(`VOL. ${bookId} PDF를 확인하고 있습니다.`);
    const objectUrl = URL.createObjectURL(file);

    try {
      const document = await getDocument({ url: objectUrl }).promise;
      const expectedPages = catalog?.books[bookId].pageCount;
      if (expectedPages && document.numPages !== expectedPages) {
        await document.destroy();
        throw new Error('Unexpected page count');
      }

      const previousDocument = loadedBooks[bookId]?.document;
      const previousUrl = objectUrls.current[bookId];
      objectUrls.current[bookId] = objectUrl;
      setLoadedBooks((current) => ({
        ...current,
        [bookId]: { document, fileName: file.name },
      }));
      setConnectionState((current) => ({ ...current, [bookId]: 'ready' }));
      setMessage(
        persistentHandle
          ? `VOL. ${bookId} 교재를 연결하고 이 기기에 기억했습니다.`
          : `VOL. ${bookId} 교재가 연결되었습니다.`,
      );

      if (persistentHandle) {
        try {
          await storeFileHandle(bookId, persistentHandle);
        } catch {
          setMessage(`VOL. ${bookId} 교재는 연결했지만 이 기기에 파일 권한을 저장하지 못했습니다.`);
        }
      }

      if (previousDocument) void previousDocument.destroy();
      if (previousUrl) URL.revokeObjectURL(previousUrl);
      return true;
    } catch {
      URL.revokeObjectURL(objectUrl);
      setConnectionState((current) => ({ ...current, [bookId]: 'error' }));
      setMessage(`VOL. ${bookId}에 맞는 할리데이 일반물리학 11판 PDF인지 확인해 주세요.`);
      return false;
    }
  }

  async function choosePdf(bookId: BookId) {
    if (!catalog) return;
    if (!supportsPersistentFileHandles()) {
      uploadInputs.current[bookId]?.click();
      return;
    }

    try {
      if (connectionState[bookId] === 'idle') {
        const rememberedHandle = await getStoredFileHandle(bookId);
        if (rememberedHandle) {
          const permission = await rememberedHandle.requestPermission({ mode: 'read' });
          if (permission === 'granted') {
            await loadPdfFile(bookId, await rememberedHandle.getFile(), rememberedHandle);
            return;
          }
          setConnectionState((current) => ({ ...current, [bookId]: 'error' }));
          setMessage(`VOL. ${bookId} 파일 권한이 필요합니다. 다시 누르면 다른 파일을 선택할 수 있습니다.`);
          return;
        }
      }

      const [handle] = await window.showOpenFilePicker!({
        multiple: false,
        types: [{ description: 'PDF 문서', accept: { 'application/pdf': ['.pdf'] } }],
      });
      if (handle) await loadPdfFile(bookId, await handle.getFile(), handle);
    } catch (error) {
      if ((error as DOMException).name !== 'AbortError') {
        setConnectionState((current) => ({ ...current, [bookId]: 'error' }));
        setMessage(`VOL. ${bookId} PDF를 열지 못했습니다. 다시 선택해 주세요.`);
      }
    }
  }

  async function selectPdf(bookId: BookId, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) await loadPdfFile(bookId, file);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    if (!catalog) return;
    const bookId = getBookId(chapterInputNumber);
    const chapter = catalog.books[bookId].chapters[String(chapterInputNumber)];
    if (!chapter) {
      setMessage('1단원부터 44단원 사이에서 선택해 주세요.');
      return;
    }
    if (
      !Number.isInteger(problemInputNumber) ||
      problemInputNumber < 1 ||
      problemInputNumber > chapter.problemCount
    ) {
      setMessage(`${chapterInputNumber}단원은 1번부터 ${chapter.problemCount}번까지 있습니다.`);
      return;
    }
    setChapterInput(String(chapterInputNumber));
    setProblemInput(String(problemInputNumber));
    setSelection({ chapter: chapterInputNumber, problem: problemInputNumber });
    setZoom(1);
    setMessage(
      loadedBooks[bookId]
        ? `${chapterInputNumber}단원 ${problemInputNumber}번을 찾았습니다.`
        : `${catalog.books[bookId].label} PDF를 먼저 연결해 주세요.`,
    );
  }

  function moveProblem(delta: number) {
    if (!activeChapter) return;
    const nextProblem = selection.problem + delta;
    if (nextProblem < 1 || nextProblem > activeChapter.problemCount) return;
    const next = { chapter: selection.chapter, problem: nextProblem };
    setSelection(next);
    setChapterInput(String(next.chapter));
    setProblemInput(String(next.problem));
    setZoom(1);
    setMessage(`${next.chapter}단원 ${next.problem}번을 찾았습니다.`);
  }

  return (
    <div className="app-shell">
      <aside className="control-panel">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            H
          </div>
          <div>
            <p>Halliday</p>
            <span>Problem Finder</span>
          </div>
        </div>

        <section className="pdf-section" aria-labelledby="pdf-heading">
          <div className="section-heading">
            <span>01</span>
            <h2 id="pdf-heading">교재 연결</h2>
          </div>
          <p className="section-copy">
            PDF는 서버에 업로드되지 않고 이 브라우저에서만 열립니다.
            <br />지원 브라우저에서는 이 기기의 연결을 기억합니다.
          </p>
          <div className="book-connectors">
            {(['1', '2'] as BookId[]).map((bookId) => {
              const loaded = loadedBooks[bookId];
              const state = connectionState[bookId];
              return (
                <div className="book-connector-wrap" key={bookId}>
                  <input
                    ref={(element) => {
                      uploadInputs.current[bookId] = element ?? undefined;
                    }}
                    className="book-upload-input"
                    type="file"
                    accept="application/pdf,.pdf"
                    aria-label={`VOL. ${bookId} PDF 선택`}
                    onChange={(event) => void selectPdf(bookId, event)}
                  />
                  <button
                    className={`book-connector ${state}`}
                    type="button"
                    onClick={() => void choosePdf(bookId)}
                    disabled={state === 'loading'}
                  >
                    <span className="book-volume">VOL. {bookId}</span>
                    <span className="book-file">
                      {state === 'loading'
                        ? 'PDF 확인 중'
                        : state === 'ready'
                          ? loaded?.fileName
                          : state === 'error'
                            ? '다시 연결하거나 다른 PDF 선택'
                            : 'PDF 선택'}
                    </span>
                    <span className="connector-icon" aria-hidden="true">
                      {state === 'loading' ? (
                        <LoaderCircle size={17} />
                      ) : state === 'ready' ? (
                        <Check size={17} />
                      ) : state === 'idle' ? (
                        <Upload size={17} />
                      ) : (
                        <CircleAlert size={17} />
                      )}
                    </span>
                  </button>
                </div>
              );
            })}
          </div>
        </section>

        <form className="search-form" onSubmit={submitSearch}>
          <div className="section-heading">
            <span>02</span>
            <h2>문제 찾기</h2>
          </div>
          <label>
            <span>단원 번호</span>
            <div className="number-input-wrap">
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="off"
                aria-label="단원 번호"
                value={chapterInput}
                onChange={(event) => {
                  setChapterInput(event.target.value.replace(/\D/g, '').slice(0, 2));
                  setProblemInput('1');
                }}
                onBlur={() => {
                  if (chapterInput !== '') setChapterInput(String(Number(chapterInput)));
                }}
                disabled={!catalog}
              />
              <small>/ 44</small>
            </div>
            <span className="input-help">
              {draftChapter?.title ?? '1부터 44까지 입력하세요'}
            </span>
          </label>
          <label>
            <span>문제 번호</span>
            <div className="number-input-wrap">
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="off"
                aria-label="문제 번호"
                value={problemInput}
                onChange={(event) => setProblemInput(event.target.value.replace(/\D/g, '').slice(0, 3))}
                onBlur={() => {
                  if (problemInput !== '') setProblemInput(String(Number(problemInput)));
                }}
              />
              <small>/ {draftChapter?.problemCount ?? '--'}</small>
            </div>
            <span className="input-help">
              {draftChapter ? `이 단원은 ${draftChapter.problemCount}문제` : '단원 번호를 먼저 확인하세요'}
            </span>
          </label>
          <button className="search-button" type="submit" disabled={!catalog}>
            <Search size={18} /> 문제 보기
          </button>
          <button
            className="review-open-button"
            type="button"
            disabled={!activePdf || !activeChapter?.reviewSegments.length}
            onClick={() => setShowChapterReview(true)}
          >
            <BookOpen size={18} /> 이 단원 개념 복습하기
          </button>
          <button
            className="constants-open-button"
            type="button"
            onClick={() => setShowPhysicalConstants(true)}
          >
            <Atom size={18} /> 물리 상수 보기
          </button>
        </form>

        <p className="privacy-note">
          <BookOpen size={15} /> 11판 한국어판 기준 · 총 44개 단원
        </p>
      </aside>

      <main className="viewer-panel">
        <header className="viewer-header">
          <div className="problem-title">
            <span>CHAPTER {selection.chapter}</span>
            <h1>{activeChapter?.title ?? '연습문제'}</h1>
            <p>문제 {selection.problem}</p>
          </div>
          <div className="viewer-actions" aria-label="보기 조절">
            <button
              type="button"
              onClick={() => moveProblem(-1)}
              disabled={!activeChapter || selection.problem <= 1}
              aria-label="이전 문제"
            >
              <ArrowLeft size={18} />
            </button>
            <button
              type="button"
              onClick={() => setZoom((value) => Math.max(0.8, value - 0.1))}
              disabled={!activePdf}
              aria-label="축소"
            >
              <Minus size={18} />
            </button>
            <output aria-label="확대 비율">{Math.round(zoom * 100)}%</output>
            <button
              type="button"
              onClick={() => setZoom((value) => Math.min(1.5, value + 0.1))}
              disabled={!activePdf}
              aria-label="확대"
            >
              <Plus size={18} />
            </button>
            <button
              type="button"
              onClick={() => moveProblem(1)}
              disabled={!activeChapter || selection.problem >= activeChapter.problemCount}
              aria-label="다음 문제"
            >
              <ArrowRight size={18} />
            </button>
          </div>
        </header>

        <div className="viewer-stage">
          {catalogError ? (
            <div className="empty-state error-state">
              <strong>문제 인덱스를 불러오지 못했습니다.</strong>
              <p>페이지를 새로고침해 주세요.</p>
            </div>
          ) : !catalog ? (
            <div className="empty-state">
              <LoaderCircle className="spin" size={26} />
              <strong>문제 목록을 준비하는 중</strong>
            </div>
          ) : !activePdf ? (
            <div className="empty-state ready-state">
              {connectionState[activeBookId] === 'loading' ? (
                <>
                  <LoaderCircle className="spin" size={28} />
                  <strong>{activeBook?.label} 자동 연결 중</strong>
                  <p>등록된 교재 파일을 확인하고 있습니다.</p>
                </>
              ) : (
                <>
                  <div className="empty-book error-book" aria-hidden="true">
                    <HardDrive size={32} />
                    <div />
                  </div>
                  <span className="empty-kicker">연결 확인 필요</span>
                  <strong>{activeBook?.label} PDF를 선택해 주세요</strong>
                  <p>
                    왼쪽 교재 연결에서 VOL. {activeBookId} 파일을 선택하면
                    <br />현재 브라우저에서 바로 문제를 볼 수 있습니다.
                  </p>
                </>
              )}
            </div>
          ) : activeProblem ? (
              <article className="problem-sheet" style={{ width: `${Math.round(760 * zoom)}px` }}>
                <div className="sheet-meta">
                  <span>{activeBook?.label}</span>
                  <span>
                    {selection.chapter}-{selection.problem}
                  </span>
                </div>
                {activeProblem.segments.map((segment, index) => (
                  <ProblemCanvas
                    key={`${selection.chapter}-${selection.problem}-${index}-${zoom}`}
                    document={activePdf}
                    segment={segment}
                    zoom={zoom}
                    index={index}
                  />
                ))}
                {activeProblem.figures?.map((segment, index) => (
                  <section className="related-figure" key={`figure-${segment.page}-${segment.y}`}>
                    <span>{segment.label}</span>
                    <ProblemCanvas
                      document={activePdf}
                      segment={segment}
                      zoom={zoom}
                      index={0}
                      label={`${segment.label} 이미지 ${index + 1}`}
                    />
                  </section>
                ))}
              </article>
          ) : (
            <div className="empty-state error-state">
              <strong>해당 문제를 찾지 못했습니다.</strong>
              <p>문제 번호를 다시 확인해 주세요.</p>
            </div>
          )}
        </div>

        <footer className="viewer-footer">
          <p aria-live="polite">{message}</p>
          {activeChapter && (
            <span>1-{activeChapter.problemCount}번 · 인덱스 v{catalog?.version}</span>
          )}
        </footer>
      </main>

      {showChapterReview && activePdf && activeChapter && (
        <div
          className="review-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowChapterReview(false);
          }}
        >
          <section
            className="review-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-modal-title"
          >
            <header className="review-modal-header">
              <div>
                <span>CHAPTER {selection.chapter}</span>
                <h2 id="review-modal-title">{activeChapter.title} · 정리 및 요약</h2>
                <p>정리 및 요약 시작부터 연습문제 직전까지</p>
              </div>
              <button
                ref={reviewCloseRef}
                type="button"
                aria-label="개념 복습 닫기"
                onClick={() => setShowChapterReview(false)}
              >
                <X size={21} />
              </button>
            </header>
            <div className="review-modal-body">
              <div className="review-pages">
                {activeChapter.reviewSegments.map((segment, index) => (
                  <ProblemCanvas
                    key={`review-${selection.chapter}-${segment.page}-${index}`}
                    document={activePdf}
                    segment={segment}
                    zoom={1}
                    index={index}
                    label={`${selection.chapter}단원 개념 정리 ${index + 1}`}
                    loadingLabel="개념 정리를 선명하게 불러오는 중"
                  />
                ))}
              </div>
            </div>
          </section>
        </div>
      )}

      {showPhysicalConstants && (
        <div
          className="review-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowPhysicalConstants(false);
          }}
        >
          <section
            className="review-modal constants-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="constants-modal-title"
          >
            <header className="review-modal-header">
              <div>
                <span>REFERENCE</span>
                <h2 id="constants-modal-title">자주 쓰는 물리 상수</h2>
                <p>SI 단위 · 2022 CODATA 및 현행 SI 정의 기준</p>
              </div>
              <button
                ref={constantsCloseRef}
                type="button"
                aria-label="물리 상수 닫기"
                onClick={() => setShowPhysicalConstants(false)}
              >
                <X size={21} />
              </button>
            </header>
            <div className="review-modal-body constants-modal-body">
              <div className="constants-table-wrap">
                <table className="constants-table">
                  <thead>
                    <tr>
                      <th scope="col">상수</th>
                      <th scope="col">기호</th>
                      <th scope="col">값</th>
                      <th scope="col">단위</th>
                    </tr>
                  </thead>
                  <tbody>
                    {PHYSICAL_CONSTANTS.map((constant) => (
                      <tr key={constant.name}>
                        <th scope="row">{constant.name}</th>
                        <td className="constant-symbol">{constant.symbol}</td>
                        <td className="constant-value">{constant.value}</td>
                        <td className="constant-unit">{constant.unit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="constants-source">
                문제풀이에서는 교재 또는 문제에 따로 제시된 반올림값을 우선 사용하세요. 출처:{' '}
                <a href="https://physics.nist.gov/constants" target="_blank" rel="noreferrer">
                  NIST 2022 CODATA
                </a>
                {' · '}
                <a
                  href="https://www.bipm.org/en/measurement-units/si-defining-constants"
                  target="_blank"
                  rel="noreferrer"
                >
                  BIPM SI
                </a>
              </p>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
