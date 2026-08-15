// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * WHICH SUBJECT A NAVIGATION LINK OPENS ON — and nothing else.
 *
 * The shell's navigation used to emit a bare `#/path` for every surface. Five of those
 * surfaces render ONE subject and are addressed by its identifier, so a reader clicking
 * down the sidebar arrived at a screen that had to work out its own subject, and the
 * address bar never said which one it had chosen. This module is the other half: it decides
 * which member of the kernel's answer goes in which query parameter for which surface, and
 * it decides nothing else.
 *
 * ── THE VALUE IS EVIDENCE, THE PARAMETER NAME IS STRUCTURE ───────────────────────
 *
 * There is **no identifier in this file** and there is nothing here to fall back to. Every
 * value comes off the wire — `src/data/demo-subjects.ts`, `GET /v1/demo/subjects`, memoised
 * per transport so the shell and the five surfaces share ONE exchange. Ruling R1:
 * *"No identifier a screen addresses may be a literal the console invented."*
 * `tests/unit/app/subjects.test.tsx` reads this file's own bytes back and searches them for
 * one.
 *
 * `'permit'`, `'site'`, `'clause'`, `'commit'` and `'lesson'` DO appear below as literals,
 * and that is not the defect R1 forbids: a query parameter's NAME is part of this console's
 * URL grammar, owned by the surface that reads it, and it names no row. They are pinned
 * rather than trusted — the test imports `PERMIT_PARAM`, `SITE_PARAM`, `CLAUSE_PARAM`,
 * `COMMIT_PARAM` and `LESSON_PARAM` from the five feature modules and asserts this table
 * against them, so a surface that renames its parameter turns a silently dead nav link into
 * a red test instead of a link that looks addressed and is not.
 *
 * The table is transcribed rather than imported for a measured reason: the shell IS the
 * entry chunk, a static import of `src/features/**` from here drags that feature's chunk
 * onto the critical path, and the entry chunk had **3,145 B** of gzip headroom under
 * `static_site.DEFAULT_MAX_RESPONSE_BYTES` when this landed (`src/app/SurfaceHost.tsx`
 * records the measurement and the two builds that proved it). A test may import anything;
 * the shell may not.
 *
 * ── THE DETAIL MODE IS NOT DEFINED HERE ──────────────────────────────────────────
 *
 * `src/app/detail-mode.ts` owns PLAIN / FULL DETAIL, ruling R6, including `hrefWithDetail`.
 * This module composes with it and does not restate it: the subject pairs are appended to
 * the path, and that path — query and all — is handed to `hrefWithDetail`, which is the one
 * function that decides whether `detail=full` is on the end. Two builders that both knew
 * about `detail` would be two places for a nav link to drop a reader out of FULL DETAIL.
 */

import type { DemoSubjects, SubjectIndex } from '../data/demo-subjects';

import { hrefWithDetail, type DetailMode } from './detail-mode';

// ── Which subject addresses which surface ──────────────────────────────────

/**
 * A member of the kernel's answer that is an identifier.
 *
 * `absent` is excluded by type: it is the emitter's prose about what it did NOT find, and
 * prose does not go in a URL.
 */
export type SubjectMember = Exclude<keyof DemoSubjects, 'absent'>;

/** One `?name=value` pair a surface reads to learn its subject. */
export interface SubjectParam {
  /** The query parameter the surface reads. Pinned against the feature's own constant. */
  readonly param: string;
  /** The member of `DemoSubjects` that fills it. */
  readonly member: SubjectMember;
}

/**
 * Per surface, the parameters that address it — in the order the surface reads them.
 *
 * A surface absent from this table takes no subject in its address: `overview` builds its
 * own doors, `evidence` audits a bundle rather than a row, `audit` is aggregate-first and
 * names no permit, and the two `declared-missing` screens have nothing to address yet.
 * Absence here is the honest default — a link carrying a parameter nothing reads is a link
 * that looks addressed and is not.
 */
export const SUBJECT_SLOTS: ReadonlyMap<string, readonly SubjectParam[]> = new Map<
  string,
  readonly SubjectParam[]
>([
  ['gate', [{ param: 'permit', member: 'permitId' }]],
  ['silence', [{ param: 'permit', member: 'permitId' }]],
  ['custody', [{ param: 'site', member: 'siteCode' }]],
  ['propagation', [{ param: 'lesson', member: 'lessonId' }]],
  // Together or not at all — `ClauseDiffScreen` says so in its own words ("a clause with
  // no commit addresses no version"), and this table keeps the link honest about it.
  [
    'diff',
    [
      { param: 'clause', member: 'clauseUuid' },
      { param: 'commit', member: 'commitId' },
    ],
  ],
]);

/**
 * The pairs this surface's link should carry, or an empty list.
 *
 * **Empty is the answer to every question the console cannot answer from the wire** — the
 * index has not resolved, the route did not answer, no transport was composed, or the
 * kernel named nothing for this slot. In every one of those the link is the bare path,
 * which is exactly what shipped before this module existed, and the surface then renders
 * its own named absence carrying the emitter's own reason. **This is the degradation path,
 * and it is a function that returns `[]`.**
 *
 * All-or-nothing per surface: a partial address is an address that looks complete.
 */
export function subjectParamsFor(
  surfaceId: string,
  index: SubjectIndex,
): readonly (readonly [string, string])[] {
  if (index.status !== 'resolved') return [];
  const slots = SUBJECT_SLOTS.get(surfaceId);
  if (slots === undefined) return [];

  const pairs: (readonly [string, string])[] = [];
  for (const slot of slots) {
    const value = index.subjects[slot.member];
    if (value === null || value === '') return [];
    pairs.push([slot.param, value] as const);
  }
  return pairs;
}

// ── Building the address ───────────────────────────────────────────────────

function withQuery(path: string, pairs: readonly (readonly [string, string])[]): string {
  if (pairs.length === 0) return path;
  const query = new URLSearchParams();
  for (const [name, value] of pairs) query.set(name, value);
  return `${path}?${query.toString()}`;
}

/**
 * The href for one navigation link: the surface's path, the subject the kernel named for
 * it, and the reader's current detail mode.
 *
 * The mode is applied by `hrefWithDetail` — this function never writes `detail` itself.
 */
export function subjectHref(
  surfaceId: string,
  path: string,
  index: SubjectIndex,
  mode: DetailMode,
): string {
  return hrefWithDetail(withQuery(path, subjectParamsFor(surfaceId, index)), mode);
}

/**
 * The address of THIS screen in the other detail mode, with everything else preserved.
 *
 * The toggle is a pair of links rather than a button, and this is why: switching mode must
 * not discard an identifier a reader typed into `#/gate?permit=…`, and it must produce a
 * URL they can copy. `hrefWithDetail` sets or removes `detail` and leaves every other
 * parameter exactly where it was, so this is a one-line composition rather than a second
 * merge.
 */
export function detailToggleHref(
  path: string,
  params: URLSearchParams,
  next: DetailMode,
): string {
  const query = params.toString();
  return hrefWithDetail(query === '' ? path : `${path}?${query}`, next);
}
