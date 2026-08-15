// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The `unsigned` verdict, and the two edges it must never cross.
 *
 * `docs/leads/screens-work-plan.md` §2.6(b) ruled that a checkpoint carrying NO signature
 * section reports SKIP with a named reason rather than FAILED, because `src/verify/config.ts`
 * already said so — *a checkpoint nobody could check has not been accused of anything* — and
 * the parser was reaching a refusal before the anchor question was ever asked.
 *
 * A reclassification like that is only safe if it is narrow, so this file exists to prove the
 * two things it must not have done, using the SAME §7.5 note in every case so that no
 * assertion here can pass by accident of a different fixture:
 *
 *   1. **A note carrying a signature that does not verify is still `failed`.** Forever. This
 *      is the check that catches a forged checkpoint and nothing above may soften it.
 *   2. **A note whose TEXT does not parse is still `malformed`.** "No signature section" is
 *      not a licence to skip; the origin, the tree size, the 32-byte root and every extension
 *      line must all still parse before the absence of a signature means anything.
 *
 * The third case is the demo's own shape — three lines, no extensions, nothing after them —
 * because that is the note the deployed seed publishes and the one whose red seal on the
 * custody screen started this.
 */

import { describe, expect, it } from 'vitest';

import {
  UnsignedNoteError,
  NoteFormatError,
  parseNote,
  parseVerificationKey,
  verifyNote,
} from '../../../src/verify/checkpoint';
import { NO_ANCHOR, operatorConfig } from '../../../src/verify/config';
import { verifyLedger, type LedgerPayload } from '../../../src/verify/ledger';
import { SOFTWARE_ORACLE } from '../../../src/verify/sha256';

import { checkpointVectors, ledgerPayloadVector } from './_vectors';

const oracle = SOFTWARE_ORACLE;
const vectors = checkpointVectors();
const subtle = globalThis.crypto?.subtle;

function caseNamed(id: string): { readonly full_note: string; readonly note_text?: string } {
  const found = vectors.cases.find((entry) => entry.id === id);
  if (found === undefined) throw new Error(`vector set is truncated: no case ${id}`);
  return found;
}

async function trustedKeys(): Promise<Awaited<ReturnType<typeof parseVerificationKey>>[]> {
  return [await parseVerificationKey(oracle, vectors.keys.trusted.vkey)];
}

/** The demo's shape: origin, tree size, base64 root, final newline, and nothing after it. */
function demoShapedNote(): string {
  const anchor = caseNamed('spec-7.5-complete-note');
  const lines = (anchor.note_text ?? '').split('\n');
  return `${lines[0]}\n${lines[1]}\n${lines[2]}\n`;
}

describe('a note nobody signed is UNSIGNED — not failed, and not passed', () => {
  it('parses the text and raises UnsignedNoteError carrying it', () => {
    let raised: unknown = null;
    try {
      parseNote(demoShapedNote());
    } catch (error) {
      raised = error;
    }
    expect(raised).toBeInstanceOf(UnsignedNoteError);
    const unsigned = raised as UnsignedNoteError;
    // The text is READ, so a surface can show what the bytes say.
    expect(unsigned.note.treeSize).toBe(5);
    expect(unsigned.note.rootHex).toHaveLength(64);
    expect(unsigned.note.signatures).toHaveLength(0);
    // A subclass, so every existing `catch (NoteFormatError)` keeps its old behaviour.
    expect(unsigned).toBeInstanceOf(NoteFormatError);
  });

  it('reports the reason in words, and does not accuse the checkpoint', async () => {
    const result = await verifyNote({ note: demoShapedNote(), keys: [], oracle, subtle });
    expect(result.verdict).toBe('unsigned');
    expect(result.reason).toContain('carries no signature at all');
    expect(result.reason).toContain('nothing has been accused');
    // The digest of the note text is still computed — those bytes are real and reproducible.
    expect(result.signedTextSha256).toHaveLength(64);
    expect(result.verifiedBy).toEqual([]);
  });

  it.runIf(subtle !== undefined)('stays unsigned even when a key IS configured', async () => {
    // The gap is the missing signature, not the missing key. Reporting "no key configured"
    // about a note with no signature line would name the wrong gap.
    const result = await verifyNote({
      note: demoShapedNote(),
      keys: await trustedKeys(),
      oracle,
      subtle,
    });
    expect(result.verdict).toBe('unsigned');
  });
});

describe('EDGE 1 — a signature that does not verify is still FAILED, forever', () => {
  it.runIf(subtle !== undefined).each([
    'resigned-body-different-key-spoofed-id',
    'resigned-body-different-key-own-id',
    'single-byte-mutation-of-the-root-line',
  ])('%s', async (id) => {
    const result = await verifyNote({
      note: caseNamed(id).full_note,
      keys: await trustedKeys(),
      oracle,
      subtle,
    });
    expect(result.verdict).toBe('failed');
  });

  it.runIf(subtle !== undefined)(
    'a checkpoint whose signature fails takes the WHOLE check red, even beside an unsigned one',
    async () => {
      const vector = ledgerPayloadVector();
      const payload = JSON.parse(JSON.stringify(vector.envelope.data)) as {
        checkpoints: Record<string, unknown>[];
      };
      const head = payload.checkpoints.at(-1);
      if (head === undefined) throw new Error('vector is truncated');
      const note = String(head.note);
      // One base64 character of the signature line, exactly as ledger.test.ts does it.
      const broken = note.replace(
        /([A-Za-z0-9+/]{20})([A-Za-z0-9+/])/,
        (_m, a: string, b: string) => `${a}${b === 'A' ? 'B' : 'A'}`,
      );
      expect(broken).not.toBe(note);
      head.note = broken;
      // ...and an unsigned checkpoint sitting next to it, which must not launder anything.
      payload.checkpoints.unshift({
        ...head,
        tree_size: 1,
        note: demoShapedNote(),
      });

      const report = await verifyLedger(payload as unknown as LedgerPayload, {
        oracle,
        config: operatorConfig(vector.vkey, vector.canon_src_sha256),
        subtle,
      });
      const check = report.checks.find((entry) => entry.name === 'log_signature');
      expect(check?.status).toBe('fail');
      expect(report.overall).toBe('fail');
    },
  );
});

describe('EDGE 2 — a note whose TEXT does not parse is still MALFORMED', () => {
  it.each([
    ['hyphen-instead-of-em-dash'],
    ['en-dash-instead-of-em-dash'],
    ['tree-size-with-leading-zero'],
    ['root-not-32-bytes'],
    ['control-character-in-note-text'],
  ])('%s stays malformed', async (id) => {
    const result = await verifyNote({
      note: caseNamed(id).full_note,
      keys: [],
      oracle,
      subtle,
    });
    expect(result.verdict).toBe('malformed');
  });

  it('a signature line swallowed into the note text is malformed, not unsigned', async () => {
    // The §7.5 note with its empty line DELETED, so the em-dash line becomes note-text line 7.
    // There is no signature section here either — and unlike the demo's note, these bytes are
    // not a note, so the absence of a signature never gets to mean anything.
    const anchor = caseNamed('spec-7.5-complete-note');
    const swallowed = anchor.full_note.replace('\n\n—', '\n—');
    expect(swallowed).not.toBe(anchor.full_note);
    expect(swallowed).not.toContain('\n\n');

    const result = await verifyNote({ note: swallowed, keys: [], oracle, subtle });
    expect(result.verdict).toBe('malformed');
    expect(result.reason).toContain('not an extension line');
    expect(result.note).toBeNull();
  });

  it('a root line that is hex rather than base64 is malformed', async () => {
    // The exact defect the deployed seed carried until 2026-08-15: every hex character is
    // also a base64 character, so a 64-character hex root DECODES — to 48 bytes.
    const lines = (caseNamed('spec-7.5-complete-note').note_text ?? '').split('\n');
    const hexRoot = 'ab'.repeat(32);
    const result = await verifyNote({
      note: `${lines[0]}\n${lines[1]}\n${hexRoot}\n`,
      keys: [],
      oracle,
      subtle,
    });
    expect(result.verdict).toBe('malformed');
    expect(result.reason).toContain('48 bytes');
  });
});

describe('the suite reports check 4 and check 10 as AMBER over an unsigned checkpoint', () => {
  /** The demo's shape, as a whole payload: one checkpoint, no leaves, nothing signed. */
  function unsignedPayload(): LedgerPayload {
    const note = demoShapedNote();
    const rootHex = (() => {
      const b64 = note.split('\n')[2] ?? '';
      const binary = atob(b64);
      let out = '';
      for (let i = 0; i < binary.length; i += 1) {
        out += (binary.codePointAt(i) ?? 0).toString(16).padStart(2, '0');
      }
      return out;
    })();
    return {
      site_code: 'site-under-test',
      checkpoints: [
        {
          site_code: 'site-under-test',
          tree_size: 5,
          root_hex: rootHex,
          note,
          canon_src_sha256: 'cd'.repeat(32),
          admissible: true,
          observed_at: null,
          s3_version: null,
        },
      ],
      leaves: [],
      inclusion_proofs: [],
    };
  }

  it('check 4 is a SKIP whose reason names the absence', async () => {
    const report = await verifyLedger(unsignedPayload(), { oracle, config: NO_ANCHOR, subtle });
    const check = report.checks.find((entry) => entry.name === 'log_signature');
    expect(check?.status).toBe('skip');
    expect(check?.detail).toContain('carries no signature at all');
    expect(report.overall).not.toBe('fail');
  });

  it('check 10 is a SKIP when the note names no canonicaliser and this reader pins none', async () => {
    const report = await verifyLedger(unsignedPayload(), { oracle, config: NO_ANCHOR, subtle });
    const check = report.checks.find((entry) => entry.name === 'canonicaliser_identity');
    expect(check?.status).toBe('skip');
    expect(check?.detail).toContain('two silences');
  });

  it('check 10 is a FINDING when this reader DOES pin a value and the note names none', async () => {
    // The narrow half of the same reclassification: a pin is a question, and a checkpoint
    // that answers nothing has failed to answer it.
    const pinned = operatorConfig(vectors.keys.trusted.vkey, 'ef'.repeat(32));
    const report = await verifyLedger(unsignedPayload(), { oracle, config: pinned, subtle });
    const check = report.checks.find((entry) => entry.name === 'canonicaliser_identity');
    expect(check?.status).toBe('fail');
    expect(check?.detail).toContain('no canon: extension line');
  });

  it('a checkpoint whose ROW disagrees with its own note text is still red', async () => {
    // Reading an unsigned note's text can only ever make the verdict worse. This is the
    // comparison that needs no key at all, and it must survive the reclassification.
    const payload = JSON.parse(JSON.stringify(unsignedPayload())) as {
      checkpoints: Record<string, unknown>[];
    };
    const first = payload.checkpoints[0];
    if (first === undefined) throw new Error('payload is truncated');
    first.root_hex = '11'.repeat(32);
    const report = await verifyLedger(payload as unknown as LedgerPayload, {
      oracle,
      config: NO_ANCHOR,
      subtle,
    });
    const check = report.checks.find((entry) => entry.name === 'log_signature');
    expect(check?.status).toBe('fail');
    expect(check?.detail).toContain('SIGNED note text says');
  });
});
