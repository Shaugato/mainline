// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The checkpoint, shown as the bytes that were signed.
 *
 * The note text is rendered VERBATIM, whitespace preserved, because those bytes are the
 * message the ECDSA signature covers. A prettified note is a different note: the em dash
 * is U+2014, the tree size has no leading zero, and the final newline is part of what was
 * hashed. Anything this panel reformatted would produce a digest a reader could not
 * reproduce, which would make the digest beside it decoration.
 *
 * The `drand:` line is shown with its round TIME, because that arithmetic is checkable
 * offline with no dependency, and immediately beside a statement that the round's own BLS
 * signature was NOT checked here. `spec/wire/checkpoint.md` §4.2 is explicit that the
 * drand line alone is not a lower bound a stranger can check, and a panel that displayed
 * the timestamp without that sentence would be making the claim the specification refuses.
 */

import { type ReactNode } from 'react';

import { Digest, Mono } from '../../../design/primitives';
import { parseDrandExtension, parseNote, type ParsedNote } from '../../../verify/checkpoint';
import type { LedgerCheckpoint } from '../../../verify/ledger';
import styles from '../custody.module.css';

interface Parsed {
  readonly note: ParsedNote | null;
  readonly error: string | null;
}

function parse(checkpoint: LedgerCheckpoint): Parsed {
  try {
    return { note: parseNote(checkpoint.note), error: null };
  } catch (error) {
    return { note: null, error: error instanceof Error ? error.message : String(error) };
  }
}

function drandLine(note: ParsedNote): string | null {
  const raw = note.extensions.get('drand');
  if (raw === undefined) return null;
  try {
    const parsed = parseDrandExtension(raw);
    return `round ${parsed.round} could not have existed before ${parsed.roundTimeIso} (1692803367 + (round − 1) × 3, arithmetic, checkable offline). The round's own BLS12-381 signature was NOT checked here — no browser primitive verifies it, and trappoint-verify reports the same SKIP.`;
  } catch (error) {
    return `the drand extension line will not parse: ${error instanceof Error ? error.message : String(error)}`;
  }
}

export function CheckpointPanel({
  checkpoint,
  signedTextSha256,
}: {
  readonly checkpoint: LedgerCheckpoint;
  /** SHA-256 of the signed bytes, recomputed by the worker. Empty when it did not run. */
  readonly signedTextSha256: string;
}): ReactNode {
  const { note, error } = parse(checkpoint);

  return (
    <section className={styles.section} aria-label={`Checkpoint at tree size ${checkpoint.tree_size}`}>
      <h3 className={styles.sectionTitle}>
        Checkpoint · tree size {checkpoint.tree_size}
      </h3>

      <dl className={styles.facts}>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>site</dt>
          <dd className={styles.factValue}>{checkpoint.site_code}</dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>admissible (projected by the database)</dt>
          <dd className={styles.factValue}>{String(checkpoint.admissible)}</dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>observed at</dt>
          <dd className={styles.factValue}>{checkpoint.observed_at ?? 'not stated'}</dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>S3 Object Lock version</dt>
          <dd className={styles.factValue}>
            {checkpoint.s3_version ?? 'none carried'}
            {checkpoint.s3_version === null
              ? ''
              : ' — offline this is a claim by us about our own archive'}
          </dd>
        </div>
      </dl>

      <div className={styles.facts}>
        <Digest value={checkpoint.root_hex} label="root, as recorded" />
        {signedTextSha256 === '' ? null : (
          <Digest value={signedTextSha256} label="SHA-256 of the signed bytes" />
        )}
        <Digest value={checkpoint.canon_src_sha256} label="canon_src_sha256" copyable={false} />
      </div>

      {error === null ? null : (
        <p className={styles.detail} data-testid="checkpoint-parse-error">
          {error}
        </p>
      )}

      <p className={styles.prose}>
        Below are the exact bytes the signature covers. They are shown unmodified — the
        separator is the last empty line, each signature line begins with the em dash{' '}
        <Mono>U+2014</Mono>, and the note text includes its own final newline.
      </p>
      <pre className={styles.note} data-testid="checkpoint-note">
        {checkpoint.note}
      </pre>

      {note === null ? null : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption>Extension lines, parsed from the signed text.</caption>
              <thead>
                <tr>
                  <th scope="col">name</th>
                  <th scope="col">value</th>
                </tr>
              </thead>
              <tbody>
                {[...note.extensions].map(([name, value]) => (
                  <tr key={name}>
                    <th scope="row" className={styles.checkName}>
                      {name}
                    </th>
                    <td className={styles.hash}>{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption>
                Signature lines. A verifier ignores a line whose key it does not hold, which is
                what lets a witness cosign without any change to the wire format — and an
                ignored line is not a passed line.
              </caption>
              <thead>
                <tr>
                  <th scope="col">key name</th>
                  <th scope="col">key id</th>
                  <th scope="col">signature bytes</th>
                </tr>
              </thead>
              <tbody>
                {note.signatures.map((signature) => (
                  <tr key={`${signature.name}-${signature.keyIdHex}`}>
                    <th scope="row" className={styles.checkName}>
                      {signature.name}
                    </th>
                    <td className={styles.verdictCell}>{signature.keyIdHex}</td>
                    <td className={styles.verdictCell}>
                      {signature.signature.byteLength} bytes, DER
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {drandLine(note) === null ? null : (
            <p className={styles.detail} data-testid="checkpoint-drand">
              {drandLine(note)}
            </p>
          )}
        </>
      )}
    </section>
  );
}
