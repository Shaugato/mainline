// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PERFORMANCE MARKS — the fixed vocabulary of instants this console measures.
 *
 * A budget is only as good as the two instants it is measured between, and the classic
 * way a latency number becomes fiction is that the two ends drift: somebody moves the
 * "interactive" mark earlier to make a graph look better, and nobody can tell, because
 * the mark was a string literal in one file.
 *
 * So the marks are a frozen tuple and a typo is a type error, and every SPAN is declared
 * with the budget it feeds. `spans.test.ts`-style coverage lives in
 * `tests/unit/perf/marks.test.ts`.
 *
 * ── THE CLOCK IS INJECTED, AND THAT IS NOT ONLY FOR TESTS ────────────────────────
 *
 * D12's cinema mode freezes `Date.now` and `performance.now` so that a capture is
 * reproducible. A recorder that reached for `performance.now()` directly would either
 * be frozen too — recording every span as 0 ms and reporting a console that renders
 * instantaneously — or would have to be exempted from the freeze, which would make the
 * one number in the capture that is not reproducible the one number about speed.
 *
 * Injecting the clock resolves it honestly: cinema mode passes a `frozenClock`, the
 * recorder records zeros, and `verdict.ts` reports those spans as NOT MEASURED rather
 * than as very fast. `src/cinema/` belongs to another worker; this file takes an
 * interface, not a dependency.
 */

/** The only source of time this package will read. */
export interface Clock {
  /** Milliseconds, monotonic, origin unspecified. */
  readonly now: () => number;
  /**
   * Whether this clock advances. A frozen clock produces spans of 0 ms, and 0 ms is not
   * a measurement — `verdict.ts` refuses to grade a span taken from a frozen clock.
   */
  readonly monotonic: boolean;
}

/** The real clock. `performance.now()` where it exists, `Date.now()` otherwise. */
export function systemClock(): Clock {
  const hasPerformance =
    typeof performance !== 'undefined' && typeof performance.now === 'function';
  return {
    now: hasPerformance ? (): number => performance.now() : (): number => Date.now(),
    monotonic: true,
  };
}

/** A clock that does not move. What cinema mode injects. */
export function frozenClock(at = 0): Clock {
  return { now: (): number => at, monotonic: false };
}

/** A clock driven by an array of readings. Used by tests; never by the application. */
export function scriptedClock(readings: readonly number[]): Clock {
  let index = 0;
  return {
    now: (): number => {
      const value = readings[Math.min(index, readings.length - 1)] ?? 0;
      index += 1;
      return value;
    },
    monotonic: true,
  };
}

// ── The vocabulary ───────────────────────────────────────────────────────────────

/**
 * Every instant this console marks. Adding one is a deliberate act; a mark that is not
 * in this tuple cannot be recorded.
 */
export const MARKS = [
  'shell:script-start',
  'shell:react-mounted',
  'bundle:fetch-start',
  'bundle:verify-start',
  'bundle:verify-resolved',
  'surface:load-start',
  'surface:mounted',
  'refusal:painted',
  'gate:interactive',
] as const;

export type MarkName = (typeof MARKS)[number];

export interface Span {
  readonly id: string;
  readonly from: MarkName;
  readonly to: MarkName;
  /** The budget id in `budgets.ts` this span feeds, or `null` when it is diagnostic only. */
  readonly budget: string | null;
  readonly why: string;
}

/**
 * The spans. Every duration budget in `budgets.ts` is fed by exactly one span here, and
 * `marks.test.ts` asserts that bijection — a budget with no span is a number nothing can
 * produce, and a span claiming a budget that does not exist is a measurement nobody grades.
 */
export const SPANS: readonly Span[] = [
  {
    id: 'first-refusal-paint',
    from: 'bundle:verify-resolved',
    to: 'refusal:painted',
    budget: 'first-refusal-paint',
    why:
      'Starts at verification resolving rather than at fetch: the console REFUSES to render an ' +
      'unverified frame, so the time before that instant is honesty, not latency, and folding it ' +
      'in would create pressure to shorten the wrong thing.',
  },
  {
    id: 'gate-interactive',
    from: 'shell:script-start',
    to: 'gate:interactive',
    budget: 'gate-interactive',
    why: 'The whole cold path a supervisor actually waits through, ending when the surface responds.',
  },
  {
    id: 'shell-mount',
    from: 'shell:script-start',
    to: 'shell:react-mounted',
    budget: null,
    why: 'Diagnostic: separates framework boot from surface work when gate-interactive regresses.',
  },
  {
    id: 'bundle-verification',
    from: 'bundle:verify-start',
    to: 'bundle:verify-resolved',
    budget: null,
    why:
      'Diagnostic, and deliberately un-budgeted: the in-browser verifier is the product’s central ' +
      'claim (D6) and must never be under time pressure from a number in this file.',
  },
];

export function spanById(id: string): Span | null {
  return SPANS.find((span) => span.id === id) ?? null;
}

// ── The recorder ─────────────────────────────────────────────────────────────────

export interface SpanReading {
  readonly spanId: string;
  /** Milliseconds, or `null` when either end was never marked or the clock is frozen. */
  readonly durationMs: number | null;
  /** Why it is `null`, or `null` when it is a real reading. Rendered verbatim. */
  readonly unmeasuredBecause: string | null;
}

export interface Recorder {
  /** Records an instant. Marking the same instant twice keeps the FIRST. */
  readonly mark: (name: MarkName) => void;
  readonly at: (name: MarkName) => number | null;
  readonly read: (spanId: string) => SpanReading;
  readonly readAll: () => readonly SpanReading[];
  readonly reset: () => void;
}

/**
 * Creates a recorder over a clock.
 *
 * The first-write-wins rule matters: React 19 in development mounts effects twice, and a
 * last-write-wins recorder would report the second, warm mount as the cold one — a
 * console that gets faster the more times you measure it.
 */
export function createRecorder(clock: Clock = systemClock()): Recorder {
  const marks = new Map<MarkName, number>();

  const read = (spanId: string): SpanReading => {
    const span = spanById(spanId);
    if (span === null) {
      return {
        spanId,
        durationMs: null,
        unmeasuredBecause: `"${spanId}" is not a declared span (see SPANS in src/perf/marks.ts).`,
      };
    }
    if (!clock.monotonic) {
      return {
        spanId,
        durationMs: null,
        unmeasuredBecause:
          'the clock is frozen (cinema mode). A span measured on a frozen clock is 0 ms, and 0 ms ' +
          'is not a measurement.',
      };
    }
    const from = marks.get(span.from);
    const to = marks.get(span.to);
    if (from === undefined || to === undefined) {
      const missing = [
        from === undefined ? span.from : null,
        to === undefined ? span.to : null,
      ].filter((name): name is MarkName => name !== null);
      return {
        spanId,
        durationMs: null,
        unmeasuredBecause: `never marked: ${missing.join(', ')}.`,
      };
    }
    if (to < from) {
      return {
        spanId,
        durationMs: null,
        unmeasuredBecause: `"${span.to}" was marked before "${span.from}"; the span is not a duration.`,
      };
    }
    return { spanId, durationMs: to - from, unmeasuredBecause: null };
  };

  return {
    mark: (name: MarkName): void => {
      if (!marks.has(name)) marks.set(name, clock.now());
    },
    at: (name: MarkName): number | null => marks.get(name) ?? null,
    read,
    readAll: (): readonly SpanReading[] => SPANS.map((span) => read(span.id)),
    reset: (): void => {
      marks.clear();
    },
  };
}
