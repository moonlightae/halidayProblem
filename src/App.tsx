import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  FileUp,
  LoaderCircle,
  Minus,
  Plus,
  Search,
} from 'lucide-react';
import {
  GlobalWorkerOptions,
  getDocument,
  type PDFDocumentProxy,
  type RenderTask,
} from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import type { BookId, CropSegment, ProblemIndex } from './types';

GlobalWorkerOptions.workerSrc = pdfWorker;

interface LoadedBook {
  document: PDFDocumentProxy;
  fileName: string;
  objectUrl: string;
}

interface Selection {
  chapter: number;
  problem: number;
}

const getBookId = (chapter: number): BookId => (chapter <= 20 ? '1' : '2');

function ProblemCanvas({
  document,
  segment,
  zoom,
  index,
}: {
  document: PDFDocumentProxy;
  segment: CropSegment;
  zoom: number;
  index: number;
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
          <LoaderCircle size={18} /> 문제를 선명하게 불러오는 중
        </div>
      )}
      {status === 'error' && (
        <div className="segment-error">이 부분을 렌더링하지 못했습니다.</div>
      )}
      <canvas ref={canvasRef} aria-label={`문제 이미지 ${index + 1}`} />
    </div>
  );
}

function App() {
  const [catalog, setCatalog] = useState<ProblemIndex | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const [chapterInput, setChapterInput] = useState(2);
  const [problemInput, setProblemInput] = useState(1);
  const [selection, setSelection] = useState<Selection>({ chapter: 2, problem: 1 });
  const [loadedBooks, setLoadedBooks] = useState<Partial<Record<BookId, LoadedBook>>>({});
  const [loadingBook, setLoadingBook] = useState<BookId | null>(null);
  const [message, setMessage] = useState('교재 PDF를 연결하면 선택한 문제가 여기에 나타납니다.');
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    fetch('/problem-index.json')
      .then((response) => {
        if (!response.ok) throw new Error('Index load failed');
        return response.json() as Promise<ProblemIndex>;
      })
      .then(setCatalog)
      .catch(() => setCatalogError(true));
  }, []);

  useEffect(
    () => () => {
      Object.values(loadedBooks).forEach((book) => {
        if (book) URL.revokeObjectURL(book.objectUrl);
      });
    },
    [loadedBooks],
  );

  const chapters = useMemo(() => {
    if (!catalog) return [];
    return (Object.entries(catalog.books) as Array<[BookId, (typeof catalog.books)[BookId]]>)
      .flatMap(([bookId, book]) =>
        Object.entries(book.chapters).map(([number, chapter]) => ({
          bookId,
          number: Number(number),
          title: chapter.title,
          problemCount: chapter.problemCount,
        })),
      )
      .sort((a, b) => a.number - b.number);
  }, [catalog]);

  const activeBookId = getBookId(selection.chapter);
  const activeBook = catalog?.books[activeBookId];
  const activeChapter = activeBook?.chapters[String(selection.chapter)];
  const activeProblem = activeChapter?.problems[String(selection.problem)];
  const activePdf = loadedBooks[activeBookId]?.document;
  const draftChapter = catalog?.books[getBookId(chapterInput)].chapters[String(chapterInput)];

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
            setChapterInput(chapterNumber);
            setProblemInput(problemNumber);
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

  async function connectPdf(bookId: BookId, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !catalog) return;
    setLoadingBook(bookId);
    setMessage(`${catalog.books[bookId].label} 파일을 확인하고 있습니다.`);
    const objectUrl = URL.createObjectURL(file);
    try {
      const document = await getDocument({ url: objectUrl }).promise;
      const expectedPages = catalog.books[bookId].pageCount;
      if (document.numPages !== expectedPages) {
        await document.destroy();
        throw new Error(`페이지 수가 ${expectedPages}쪽인 교재를 선택해 주세요.`);
      }
      const previous = loadedBooks[bookId];
      if (previous) {
        await previous.document.destroy();
        URL.revokeObjectURL(previous.objectUrl);
      }
      setLoadedBooks((current) => ({
        ...current,
        [bookId]: { document, fileName: file.name, objectUrl },
      }));
      setMessage(`${catalog.books[bookId].label} 연결 완료`);
    } catch (error) {
      URL.revokeObjectURL(objectUrl);
      setMessage(error instanceof Error ? error.message : 'PDF를 열지 못했습니다.');
    } finally {
      setLoadingBook(null);
      event.target.value = '';
    }
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    if (!catalog) return;
    const bookId = getBookId(chapterInput);
    const chapter = catalog.books[bookId].chapters[String(chapterInput)];
    if (!chapter) {
      setMessage('1단원부터 44단원 사이에서 선택해 주세요.');
      return;
    }
    if (problemInput < 1 || problemInput > chapter.problemCount) {
      setMessage(`${chapterInput}단원은 1번부터 ${chapter.problemCount}번까지 있습니다.`);
      return;
    }
    setSelection({ chapter: chapterInput, problem: problemInput });
    setZoom(1);
    setMessage(
      loadedBooks[bookId]
        ? `${chapterInput}단원 ${problemInput}번을 찾았습니다.`
        : `${catalog.books[bookId].label} PDF를 먼저 연결해 주세요.`,
    );
  }

  function moveProblem(delta: number) {
    if (!activeChapter) return;
    const nextProblem = selection.problem + delta;
    if (nextProblem < 1 || nextProblem > activeChapter.problemCount) return;
    const next = { chapter: selection.chapter, problem: nextProblem };
    setSelection(next);
    setChapterInput(next.chapter);
    setProblemInput(next.problem);
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
          <p className="section-copy">PDF는 업로드되지 않고 이 브라우저에서만 열립니다.</p>
          <div className="book-connectors">
            {(['1', '2'] as BookId[]).map((bookId) => {
              const loaded = loadedBooks[bookId];
              const loading = loadingBook === bookId;
              return (
                <label className={`book-connector ${loaded ? 'connected' : ''}`} key={bookId}>
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    onChange={(event) => void connectPdf(bookId, event)}
                    disabled={!catalog || loading}
                  />
                  <span className="book-volume">VOL. {bookId}</span>
                  <span className="book-file">
                    {loading ? '파일 확인 중' : loaded ? loaded.fileName : 'PDF 선택'}
                  </span>
                  <span className="connector-icon" aria-hidden="true">
                    {loading ? <LoaderCircle size={17} /> : loaded ? <Check size={17} /> : <FileUp size={17} />}
                  </span>
                </label>
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
            <span>단원</span>
            <select
              value={chapterInput}
              onChange={(event) => {
                const nextChapter = Number(event.target.value);
                setChapterInput(nextChapter);
                setProblemInput(1);
              }}
              disabled={!catalog}
            >
              <optgroup label="일반물리학 I">
                {chapters.filter((item) => item.bookId === '1').map((item) => (
                  <option key={item.number} value={item.number}>
                    {item.number}. {item.title}
                  </option>
                ))}
              </optgroup>
              <optgroup label="일반물리학 II">
                {chapters.filter((item) => item.bookId === '2').map((item) => (
                  <option key={item.number} value={item.number}>
                    {item.number}. {item.title}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          <label>
            <span>문제 번호</span>
            <div className="number-input-wrap">
              <input
                type="number"
                min={1}
                max={draftChapter?.problemCount ?? 99}
                value={problemInput}
                onChange={(event) => setProblemInput(Number(event.target.value))}
              />
              <small>/ {draftChapter?.problemCount ?? '--'}</small>
            </div>
          </label>
          <button className="search-button" type="submit" disabled={!catalog}>
            <Search size={18} /> 문제 보기
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
              <div className="empty-book" aria-hidden="true">
                <span>{activeBookId}</span>
                <div />
              </div>
              <span className="empty-kicker">준비 완료</span>
              <strong>{activeBook?.label} PDF를 연결해 주세요</strong>
              <p>
                왼쪽의 VOL. {activeBookId}에서 파일을 한 번 선택하면
                <br />이 브라우저 탭에서 바로 문제를 찾을 수 있습니다.
              </p>
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
          {activeChapter && <span>1-{activeChapter.problemCount}번</span>}
        </footer>
      </main>
    </div>
  );
}

export default App;
