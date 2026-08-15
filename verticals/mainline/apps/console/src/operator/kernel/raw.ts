// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE RAW PAYLOAD DRAWER AND THE REQUEST LOG — R18.
 *
 * *"Every screen carries a RAW PAYLOAD affordance and a REQUEST LOG. One click shows the
 * verbatim JSON that produced what is on screen, with the request method, path, status,
 * wire bytes and `observed_at`. This is what makes the two registers believable and it is
 * what a judge in devtools will cross-check."*
 *
 * THE ONE RULE THIS FILE EXISTS TO KEEP: the body it renders is
 * {@link Exchange.raw} — the exact text the server sent — inserted with `textContent`.
 * It is **never** `JSON.stringify(JSON.parse(raw))`. A re-serialised payload would look
 * identical to a judge and would no longer be the thing that arrived: key order, spacing,
 * numeric formatting and any duplicate key all come out of the round trip changed, and the
 * whole point of the affordance is that what is on screen can be diffed against the
 * Network panel's Response tab byte for byte.
 *
 * `textContent`, everywhere, for the second reason too: the drawer displays bytes from a
 * server, and a drawer that parsed them as markup would be an injection surface pointed at
 * the one screen whose job is to be trusted.
 *
 * A NOTE ON `wireBytes`, WHICH IS RENDERED WITH ITS LABEL AND NOT WITHOUT ONE. It is the
 * UTF-8 length of the decoded body. The transfer may have been gzipped — `app.py`
 * negotiates the pre-compressed siblings the packer ships — so it is the payload's size and
 * not the socket's. The label says "body bytes (decoded)". A number on this screen that
 * meant something other than what it said would be exactly the defect the drawer exists to
 * disprove.
 */

import './kernel.css';

import type { Exchange } from './client';

/** The drawer's model. Everything here came off one real exchange. */
export interface RawView {
  readonly method: 'GET' | 'POST';
  readonly path: string;
  /** The absolute URL fetched — the value devtools shows as `Request URL`. */
  readonly url: string;
  /** HTTP status, or 0 when no response arrived. */
  readonly status: number;
  /** UTF-8 length of the decoded body. See the module note. */
  readonly wireBytes: number;
  /** The envelope's `observed_at` — when the READ API produced the payload. */
  readonly observedAt: string | null;
  /** The `Date` response header — the SERVER's clock. */
  readonly serverDate: string | null;
  /** This browser's clock when the body finished arriving. Labelled as the client's. */
  readonly receivedAt: string;
  /** Round trip measured by this client, in ms. */
  readonly elapsedMs: number;
  /** `X-Mainline-Emulator`. Non-null means this is a rehearsal, not the deployment. */
  readonly emulator: string | null;
  /** The envelope's `resource` and `schema_id`, when it carried an envelope. */
  readonly resource: string | null;
  readonly schemaId: string | null;
  /** The envelope's `staged` flag and note. `false`/null is the normal, load-bearing case. */
  readonly staged: boolean | null;
  readonly stagedNote: string | null;
  /** The verbatim response text. Never re-serialised. */
  readonly body: string;
  /** `error.kind` when the body was a problem, else null. */
  readonly problemKind: string | null;
  /** The named failure, when there was one. */
  readonly failure: string | null;
}

/** Build the drawer's model from one exchange. Reads; composes nothing. */
export function rawViewOf(exchange: Exchange<unknown>): RawView {
  return {
    method: exchange.method,
    path: exchange.path,
    url: exchange.url,
    status: exchange.status,
    wireBytes: exchange.wireBytes,
    observedAt: exchange.envelope?.observed_at ?? null,
    serverDate: exchange.serverDate,
    receivedAt: exchange.receivedAt,
    elapsedMs: exchange.elapsedMs,
    emulator: exchange.emulator,
    resource: exchange.envelope?.resource ?? null,
    schemaId: exchange.envelope?.schema_id ?? null,
    staged: exchange.envelope?.staged ?? null,
    stagedNote: exchange.envelope?.staged_note ?? null,
    body: exchange.raw,
    problemKind: exchange.problem?.kind ?? null,
    failure:
      exchange.failure === null ? null : `${exchange.failure.kind} — ${exchange.failure.detail}`,
  };
}

/** `123.4 ms`, one decimal, from a real `performance.now()` difference. */
function ms(value: number): string {
  return `${value.toFixed(1)} ms`;
}

function absent(): HTMLElement {
  const span = document.createElement('span');
  span.className = 'mlk-absent';
  // An absence is written as an absence. Never an em dash standing in for a value, and
  // never a zero.
  span.textContent = 'not carried';
  return span;
}

function row(label: string, value: string | number | boolean | null): HTMLElement {
  const dt = document.createElement('dt');
  dt.textContent = label;
  const dd = document.createElement('dd');
  if (value === null) {
    dd.append(absent());
  } else {
    dd.textContent = String(value);
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'mlk-meta__row';
  wrapper.append(dt, dd);
  return wrapper;
}

/**
 * Render one raw-payload drawer into `host`, replacing whatever was there.
 *
 * Vanilla DOM, no framework, no dependency (R1). Screens own the disclosure control; this
 * owns the contents, so four screens cannot disagree about what "raw" means.
 */
export function renderRawPayload(host: HTMLElement, view: RawView): void {
  host.replaceChildren();
  host.classList.add('mlk-raw');

  const meta = document.createElement('dl');
  meta.className = 'mlk-meta';
  meta.append(
    row('request', `${view.method} ${view.path}`),
    row('url', view.url),
    row('status', view.status === 0 ? null : view.status),
    row('body bytes (decoded)', view.wireBytes),
    row('observed_at (read API)', view.observedAt),
    row('date (server header)', view.serverDate),
    row('received (this browser)', view.receivedAt),
    row('round trip (measured here)', ms(view.elapsedMs)),
    row('resource', view.resource),
    row('schema_id', view.schemaId),
    row('staged', view.staged),
    row('staged_note', view.stagedNote),
    row('X-Mainline-Emulator', view.emulator),
  );
  if (view.problemKind !== null) {
    meta.append(row('error.kind', view.problemKind));
  }
  if (view.failure !== null) {
    meta.append(row('failure', view.failure));
  }

  const caption = document.createElement('p');
  caption.className = 'mlk-raw__caption';
  caption.textContent =
    'The bytes below are the response body exactly as it arrived. Nothing has been ' +
    're-serialised, re-ordered or reformatted.';

  const pre = document.createElement('pre');
  pre.className = 'mlk-raw__body';
  pre.setAttribute('tabindex', '0');
  // textContent, not innerHTML, and not a formatter. See the module note.
  pre.textContent = view.body === '' ? '(no bytes arrived)' : view.body;

  host.append(meta, caption, pre);
}

/** One line per exchange, transport facts only. */
function logRow(exchange: Exchange<unknown>): HTMLElement {
  const li = document.createElement('li');
  li.className = 'mlk-log__row';

  const method = document.createElement('span');
  method.className = 'mlk-log__method';
  method.textContent = exchange.method;

  const path = document.createElement('span');
  path.className = 'mlk-log__path';
  path.textContent = exchange.path;

  const status = document.createElement('span');
  status.className = 'mlk-log__status';
  if (exchange.failure === null) {
    status.textContent = String(exchange.status);
    status.dataset.ok = String(exchange.ok);
  } else {
    // A failure is named. It is never rendered as a blank, a zero or a dash.
    status.textContent = exchange.failure.kind;
    status.dataset.ok = 'false';
  }

  const size = document.createElement('span');
  size.className = 'mlk-log__size';
  size.textContent = `${exchange.wireBytes} B`;

  const took = document.createElement('span');
  took.className = 'mlk-log__ms';
  took.textContent = ms(exchange.elapsedMs);

  li.append(method, path, status, size, took);

  if (exchange.emulator !== null) {
    const emulator = document.createElement('span');
    emulator.className = 'mlk-log__emulator';
    emulator.textContent = exchange.emulator;
    li.append(emulator);
  }
  return li;
}

/**
 * Render the request log into `host`, replacing whatever was there.
 *
 * Append-only upstream (`log.ts`); this renders every entry it is handed, oldest first,
 * and filters nothing. Pass `entries()` from `log.ts` and re-render on `onChange`.
 */
export function renderRequestLog(host: HTMLElement, list: readonly Exchange<unknown>[]): void {
  host.replaceChildren();
  host.classList.add('mlk-log');

  if (list.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'mlk-absent';
    empty.textContent = 'no request has been made from this page yet';
    host.append(empty);
    return;
  }

  const ol = document.createElement('ol');
  ol.className = 'mlk-log__list';
  for (const exchange of list) {
    ol.append(logRow(exchange));
  }
  host.append(ol);
}
