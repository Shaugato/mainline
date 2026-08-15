// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SUBJECT REGISTRY, AND THE DIRECTION IT IS ALLOWED TO BE CHECKED IN.
 *
 * `docs/leads/demo-story-plan.md` R3 asks for one module holding every identifier the
 * console addresses, and a test that reads `verticals/mainline/db/seeds/demo/*.sql` and
 * fails if a constant is absent from the seed. **The direction is the whole ruling:** the
 * constant is checked against the seed, never the reverse. Editing a seed file so that a
 * console constant agrees was caught and reverted in this repository once already.
 *
 * ── WHAT HAPPENED TO THE MODULE, AND WHY THIS FILE IS NOT ABOUT ONE ──────────────
 *
 * R3 was written against `e88b8b6`, when the console shipped three invented identifiers:
 * `BLK-07`, a clause UUID and a commit hex, all three of which answered **404** on the
 * live URL. Collecting them into one seed-checked module would have been a real repair of
 * a real defect.
 *
 * By the time it was executed the every-screen wave had landed a stronger one. The kernel
 * grew `GET /v1/demo/subjects` — `mainline_demo_api/subjects.py`, which `SELECT`s each
 * subject out of the relation that owns it and can therefore name nothing that is not
 * there — and every identifier was deleted from the console. `docs/leads/screens-work-plan.md`
 * §2.1 rules the consequence in words this file is the enforcement of:
 *
 *     "A worker who pastes dec0de00-0006-… into a .tsx constant has rebuilt BLK-07 with a
 *      luckier value. It fails the moment the seed changes and it is the same class of
 *      defect as the one we are fixing. No UUID literal may appear in any console source
 *      file in this wave."
 *
 * So there is no `src/app/demo-subjects.ts` to weld to the seed, and adding one — even
 * seed-checked — would reintroduce the class. A seed-checked constant is still a constant:
 * it is welded to the seed FILE, and what a judge meets is the deployed DATABASE, which is
 * where the two can differ and did (`docs/leads/demo-story-plan.md` §0.4(ii) — a superseded
 * checkpoint the current seed no longer writes, still resident in the cloud).
 *
 * ── WHAT R3'S TEST BECOMES WHEN THERE IS NO CONSTANT ─────────────────────────────
 *
 * Three assertions, all of them non-vacuous, all of them in R3's direction.
 *
 *   1. **No console source file names a row — the WHOLE tree.** There is already a
 *      ratchet for this and it is a hand-written list of seven files
 *      (`tests/unit/data/demo-subjects.test.ts`). A list cannot cover a file nobody has
 *      written yet, which is exactly how nine identifiers in a NEW `src/app/demo-subjects.ts`
 *      would have landed with every existing guard green. This walks `src/` and reads the
 *      characters on disk.
 *   2. **The seed is the authority for which subjects exist.** The subject index names the
 *      relations it reads; the demo seed names the relations it writes. Every relation the
 *      index reads must be one the seed writes — read out of both files' own bytes. If a
 *      seed section is deleted, the fix is on the reading side. **Never the reverse.**
 *   3. **The console addresses only slots the kernel declares.** `SUBJECT_SLOTS` names the
 *      members that fill its five deep links; `ADDRESSED_SLOTS` in `subjects.py` is the
 *      kernel's list of what it will answer. A member renamed on one side turns every nav
 *      link for that surface silently bare — the degradation path is `[]`, which is honest
 *      and invisible. This makes it red instead.
 *
 * Nothing here reads a value. Not one identifier appears in this file, and assertion 1 runs
 * over `src/` precisely so that none can appear there either.
 */

import { describe, expect, it } from 'vitest';

import { SUBJECT_SLOTS } from '../../../src/app/subjects';
import { REPO_ROOT } from '../data/_support';

// ── Reading the tree, and the two files outside it ─────────────────────────

interface Dirent {
  readonly name: string;
  isDirectory(): boolean;
  isFile(): boolean;
}

interface FsSlice {
  readFileSync(path: string, encoding: 'utf8'): string;
  readdirSync(path: string, options: { readonly withFileTypes: true }): readonly Dirent[];
  existsSync(path: string): boolean;
}

/**
 * `node:fs`, resolved at runtime rather than at type-check time.
 *
 * The same trick, and for the same reason, as `tests/unit/data/_support.ts`'s `nodeFs`:
 * the unit project's `types` list is `["vite/client", "vitest/globals"]`, so the
 * application cannot reach a Node global by accident. This declares its own slice rather
 * than importing that one because this file needs a DIRECTORY LISTING — assertion 1 is
 * about every file in `src/`, including the ones nobody has written yet — and `_support.ts`
 * belongs to the data-layer worker.
 *
 * `readFileSync` over `import.meta.glob('/src/**', { query: '?raw' })` is also deliberate:
 * the glob would put 1.95 MB of source text through Vite's transform pipeline at collect
 * time, and `tests/unit/app/onramp.test.tsx` records what a heavy test file costs its
 * neighbours (three runs in four, borderline siblings pushed past their timeout). This
 * reads the bytes and nothing else.
 */
async function repoFs(): Promise<FsSlice> {
  const specifier = ['node', 'fs'].join(':');
  const mod: unknown = await import(/* @vite-ignore */ specifier);
  return mod as FsSlice;
}

/** Everything the console compiles or ships. Not `.json`, `.md` or a fixture. */
const SOURCE_FILE = /\.(?:ts|tsx|css)$/;

function walk(fs: FsSlice, dir: string, out: string[]): void {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`;
    if (entry.isDirectory()) walk(fs, path, out);
    else if (entry.isFile() && SOURCE_FILE.test(entry.name)) out.push(path);
  }
}

/** Paths are resolved against the VITEST working directory — the console workspace. */
const SEED_DIR = `${REPO_ROOT}verticals/mainline/db/seeds/demo`;
const DEMO_WORLD_SQL = `${SEED_DIR}/demo_world.sql`;
const DEMO_PERMIT_SQL = `${SEED_DIR}/demo_permit.sql`;
const SUBJECTS_PY = `${REPO_ROOT}verticals/mainline/apps/demo-api/src/mainline_demo_api/subjects.py`;

/**
 * A reader that refuses to be quietly satisfied by a missing file.
 *
 * R3's test is worthless if it goes green because a seed was renamed: "no constant was
 * absent from a file that does not exist" is true and means nothing.
 */
function mustRead(fs: FsSlice, path: string, why: string): string {
  expect(fs.existsSync(path), `${path} is not there. ${why}`).toBe(true);
  const text = fs.readFileSync(path, 'utf8');
  expect(text.length, `${path} is empty`).toBeGreaterThan(0);
  return text;
}

function matchAll(text: string, pattern: RegExp): readonly string[] {
  const found = new Set<string>();
  for (const match of text.matchAll(pattern)) {
    const captured = match[1];
    if (captured !== undefined) found.add(captured);
  }
  return [...found].sort();
}

// ── 1. No console source file names a row ──────────────────────────────────

/**
 * The two shapes an identifier arrives in. Both are checked in code AND in comments,
 * because a UUID in a comment is the copy somebody pastes into code next week.
 */
const UUID_ANYWHERE = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;
const SHA256_ANYWHERE = /\b[0-9a-fA-F]{64}\b/;

describe('no console source file names a row — the whole tree, not a list', () => {
  it('walks src/ and finds the files at all', async () => {
    const fs = await repoFs();
    const files: string[] = [];
    walk(fs, 'src', files);
    // A walk that silently found nothing would make every assertion below vacuously true.
    expect(files.length, 'the walk over src/ returned no source files').toBeGreaterThan(100);
  });

  it('carries no UUID literal in any file, written or yet to be written', async () => {
    const fs = await repoFs();
    const files: string[] = [];
    walk(fs, 'src', files);

    const offenders: string[] = [];
    for (const file of files) {
      const found = UUID_ANYWHERE.exec(fs.readFileSync(file, 'utf8'));
      if (found !== null) offenders.push(`${file}: ${found[0]}`);
    }

    expect(
      offenders,
      'a console file naming a row is a console asserting a fact about a database it did ' +
        'not write. It is true on the day it ships and false the first time a deployment ' +
        'seeds a different history — which is exactly how BLK-07 reached the live URL and ' +
        'answered 404 there (docs/leads/screens-work-plan.md §2.1). Ask the kernel: ' +
        'GET /v1/demo/subjects, through src/data/demo-subjects.ts, which is memoised so ' +
        'that asking costs one exchange for the whole page.\n\n' +
        'A DOCSTRING COUNTS, and the rule is not new — the seven-file ratchet in ' +
        'tests/unit/data/demo-subjects.test.ts already says "in code or in a comment", ' +
        'because a UUID in a comment is the copy somebody pastes into code next week, and ' +
        'because a docstring that quotes an address goes quietly false when the seed ' +
        'changes. If the sentence is recording a measurement, it loses nothing by naming ' +
        'the SHAPE instead of the value: `#/gate?permit=<the seeded permit>`.',
    ).toEqual([]);
  });

  it('carries no bare SHA-256 either — a commit id is an identifier too', async () => {
    const fs = await repoFs();
    const files: string[] = [];
    walk(fs, 'src', files);

    const offenders: string[] = [];
    for (const file of files) {
      const found = SHA256_ANYWHERE.exec(fs.readFileSync(file, 'utf8'));
      if (found !== null) offenders.push(`${file}: ${found[0]}`);
    }

    expect(
      offenders,
      'the Diff screen is addressed by a clause AND a commit, and the commit is 64 hex ' +
        'characters rather than a UUID. Pinning one in console source is the same defect ' +
        'in a different alphabet: the invented commit that shipped before this wave ' +
        'answered 404 beside the invented clause. The head commit is a member of ' +
        'GET /v1/demo/subjects.',
    ).toEqual([]);
  });
});

// ── 2. The seed is the authority for which subjects exist ──────────────────

describe('every subject the console can be told about is one the demo seed writes', () => {
  it('reads the seed, reads the index, and checks the index against the seed', async () => {
    const fs = await repoFs();

    const seedText =
      mustRead(
        fs,
        DEMO_WORLD_SQL,
        'R3 names it as the authority for which subjects this demo carries; a renamed seed ' +
          'makes this whole file green for the wrong reason.',
      ) +
      '\n' +
      mustRead(fs, DEMO_PERMIT_SQL, 'It is the other half of the demo world — the permit branch.');

    const indexText = mustRead(
      fs,
      SUBJECTS_PY,
      'It is the only component allowed to name a subject, because it SELECTs each one out ' +
        'of the relation that owns it.',
    );

    // What the seed WRITES. Its own statements, not a list maintained here.
    const seeded = matchAll(seedText, /INSERT\s+INTO\s+([a-z_]+\.[a-z_]+)/gi);
    // What the subject index READS — `_RELATIONS_SQL`, which exists so the route can say
    // "the table is there and holds no such row" apart from "no such table".
    const indexed = matchAll(indexText, /to_regclass\('([a-z_]+\.[a-z_]+)'\)/g);

    // A regex that finds nothing is a failure, not a pass.
    expect(seeded.length, `no INSERT INTO found in the demo seed`).toBeGreaterThan(5);
    expect(indexed.length, `no to_regclass() found in ${SUBJECTS_PY}`).toBeGreaterThan(5);

    const unseeded = indexed.filter((relation) => !seeded.includes(relation));
    expect(
      unseeded,
      'GET /v1/demo/subjects indexes a relation the demo seed never writes a row into, so ' +
        'the console will offer a navigation link for it and the screen behind that link ' +
        'will render an absence a judge reads as a defect.\n\n' +
        'THE DIRECTION OF THIS CHECK IS FIXED AND NON-NEGOTIABLE (R3). The seed is the ' +
        'authority. If this is red, either the reading side owes the removal or the seed ' +
        'owes the row ON ITS OWN MERITS — a row that belongs in the demo world for a ' +
        'reason somebody can state. Editing a seed file so that a constant, a slot or a ' +
        'query agrees with it is the one unforgivable move in this repository; it was ' +
        'caught and reverted here once already.',
    ).toEqual([]);
  });
});

// ── 3. The console addresses only slots the kernel declares ────────────────

/** `permitId` → `permit_id`. The wire is snake_case; `demo-subjects.ts` maps it. */
function toWireName(member: string): string {
  return member.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

describe('the five addressed surfaces name slots the kernel answers', () => {
  it('checks SUBJECT_SLOTS against the kernel’s own ADDRESSED_SLOTS', async () => {
    const fs = await repoFs();
    const indexText = mustRead(fs, SUBJECTS_PY, 'It declares what the index will answer.');

    const tuple = /ADDRESSED_SLOTS[^=]*=\s*\(([^)]*)\)/.exec(indexText);
    expect(
      tuple?.[1],
      `${SUBJECTS_PY} declares no ADDRESSED_SLOTS tuple in the shape this assertion reads. ` +
        'A regex that finds nothing must fail rather than pass silently.',
    ).toBeDefined();

    const declared = matchAll(tuple?.[1] ?? '', /"([a-z_]+)"/g);
    expect(declared.length, 'ADDRESSED_SLOTS parsed to an empty list').toBeGreaterThan(5);

    const addressed = [...SUBJECT_SLOTS.values()]
      .flat()
      .map((slot) => toWireName(slot.member));
    expect(addressed.length, 'SUBJECT_SLOTS addresses nothing').toBeGreaterThan(0);

    const unanswerable = [...new Set(addressed)].sort().filter((name) => !declared.includes(name));
    expect(
      unanswerable,
      'src/app/subjects.ts fills a navigation link from a member GET /v1/demo/subjects does ' +
        'not declare. The console does not crash on this — `subjectParamsFor` returns [] and ' +
        'the link degrades to a bare #/path — which is honest and completely invisible: the ' +
        'nav goes back to shipping unaddressed links and nobody finds out until a judge ' +
        'clicks one. Reconcile the member name with mainline_demo_api/subjects.py.',
    ).toEqual([]);
  });
});
