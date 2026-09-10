export type BookId = '1' | '2';

export interface CropSegment {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FigureSegment extends CropSegment {
  label: string;
}

export interface ProblemEntry {
  segments: CropSegment[];
  figures?: FigureSegment[];
}

export interface ChapterEntry {
  title: string;
  exercisePrintedPage: number;
  reviewSegments: CropSegment[];
  problemCount: number;
  problems: Record<string, ProblemEntry>;
  diagnostics: Array<{ page: number; left: number; right: number }>;
}

export interface BookEntry {
  label: string;
  fileHint: string;
  pageCount: number;
  chapters: Record<string, ChapterEntry>;
}

export interface ProblemIndex {
  version: number;
  pdfPageOffset: number;
  books: Record<BookId, BookEntry>;
}
