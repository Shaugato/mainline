// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The honesty chrome (D16) — a permanent, non-dismissible strip.
 *
 * There is no close button, no collapse affordance and no `aria-hidden` path. Every
 * surface in this console renders beneath it, and ui.md §7 makes that structural: there
 * is no screen reachable without it. It is also the first five seconds of the demo
 * video, which is the reason it is at the top rather than in a footer.
 *
 * Each cell renders one fact plus a PROVENANCE marker saying how the console came to
 * believe it (D5): `db:column`, `db:constraint`, `recomputed`, `staged`,
 * `transport:describe`, `build`, or `unset`. A cell nobody filled reads "unset". That is
 * the honest rendering of an empty slot and it is deliberately the ugliest state on the
 * screen.
 *
 * ── THE TRANSPORT CELL'S MARKER WAS A FALSE LABEL ON A TRUE VALUE ────────────────
 *
 * It read `staged` — and `src/design/provenance.ts` defines `staged` as *"it exists only
 * in this browser — nothing written, nothing refused, nobody has signed anything"*. That
 * is the marker for a number this console made up. `LIVE` is not one: it is read off
 * `transport.describe().mode`, on the object that is holding the bytes, by
 * `app/composition.tsx` — *"never from `source-select.ts`'s answer, and never from a flag
 * beside it. Two places for one fact is one place for them to disagree."*
 *
 * So the marker is `transport:describe`, which names the thing that establishes it. The
 * VALUE did not change and no cell went green: `LIVE` was already true and is still
 * `neutral`, `REPLAY` is still amber, and a transport that has declared nothing is still
 * `unset`. What changed is that the strip stopped describing its own most load-bearing
 * fact as something staged in a browser. A provenance marker that misnames its source is
 * worse than none, because it is the one line on the strip a sceptical reader checks
 * first.
 *
 * ── WHY THREE CELLS STOPPED SAYING "unknown" ─────────────────────────────────────
 *
 * `unknown` means *the console tried to establish this and could not*. Three of these
 * cells are not in that situation when the transport is LIVE — they are in a situation
 * the word `unknown` actively misdescribes:
 *
 *   • **bundle** — no bundle byte is on screen, because no bundle was opened. Nothing
 *     was attempted and nothing failed. "A digest we could not obtain" and "a digest
 *     there was never anything to compute" are different facts.
 *   • **seal** — the cell reports the IN-BROWSER BUNDLE VERIFIER, and in LIVE that
 *     verifier does not run. `NOT VERIFIED` reads as a failure that has not occurred.
 *   • **signature path** — D17 decides the capture path at build time from the GT-15
 *     attestation. `unknown` is the state where NO attestation existed, so this artefact
 *     selected neither path. Printing `webauthn` or `oidc_envelope` would be a
 *     fabrication; printing `unknown` describes a lookup rather than the build.
 *
 * **What changed is the words, not the colour.** Every tone below is the tone the cell
 * already had, every provenance marker still reads `unset` wherever nothing was
 * established, and no cell in this file can reach `ok` on any path a reader has not
 * earned. A slot nobody filled still looks like a slot nobody filled. The sentence that
 * explains each of these three is rendered UNDER the strip, verbatim, so the fact is
 * legible without a hover — a tooltip nobody opens is not a disclosure.
 *
 * ── THE FOURTH NOTHING, NAMED (R4, 2026-08-15) ───────────────────────────────────
 *
 * `.env.demo` ships `VITE_MAINLINE_LOG_VKEY=` — empty. So the check that would say WHO
 * signed the ledger's checkpoints cannot run in this build, and until now nothing on the
 * strip said so: a reader had to open the custody surface to find out. That is now its
 * own cell, filled by a check that ACTUALLY RUNS — `resolveVerifierConfig()` reads the
 * anchor this artefact was compiled with and reports what it found — and when it finds
 * nothing the cell reads **`SKIPPED — this build carries no log key`** in amber, with
 * `src/verify/config.ts`'s own sentence beneath the strip.
 *
 * Amber, never green and never red. `config.ts` states the rule and this cell is bound by
 * it: *"a checkpoint nobody could check has not been accused of anything"*. Green would
 * mean a signature was checked and held; red would mean one was checked and did not. This
 * cell has done neither, and the word for that is SKIPPED.
 *
 * It is deliberately a SEPARATE cell from `seal`. The seal reports the bundle verifier
 * — which does not run under LIVE because there is no bundle — and the log key governs a
 * different check on a different object. Collapsing the two would make one amber cell
 * stand for two unrelated nothings, and a reader could not tell which one they were being
 * told about. `src/verify/config.ts` is already in the entry chunk (the composition root
 * imports it statically to build the REPLAY verifier), so naming this fact here costs the
 * evidentiary shell nothing at all.
 *
 * ── EVERY CELL OWES A PLAIN SENTENCE, AND A `title=` IS NOT ONE ──────────────────
 *
 * A `title` attribute is invisible on a phone, invisible to a keyboard, unreliable to a
 * screen reader, and gone from a printed exhibit. `src/a11y/contract.ts` is the law here
 * and it is unambiguous about carrying meaning in a hover alone. So each cell is a
 * focusable `role="group"` naming itself, and its plain one-sentence explanation is a real
 * text node in the DOM, referenced by `aria-describedby`: a screen reader speaks it on
 * focus, a keyboard reveals it on focus, a pointer reveals it on hover, and print shows
 * every one of them. The `title` is kept as well, because losing a working affordance to
 * add a better one helps nobody.
 *
 * No control was added: `role="group"` with `tabIndex=0` is a stop, not a button, and the
 * strip still contains zero `<button>`, zero `<input>` and nothing dismissible — which is
 * asserted, not asserted-in-a-comment, by `tests/unit/app/shell.test.tsx` and
 * `tests/unit/app/honesty-chrome.test.tsx`.
 *
 * The sentences themselves are a LAZY chunk (`./HonestyChrome.plain`) and the reason is
 * 829 measured bytes: see that module's header, and the report to the lead. Every FACT on
 * this strip is eager. Only the explanations arrive a beat later, and a cell that has none
 * yet declares none rather than pointing `aria-describedby` at an element that is not
 * there.
 */

import { useEffect, useId, useMemo, useState, type ReactNode } from 'react';

import { resolveVerifierConfig, type VerifierConfig } from '../verify/config';

import type { PlainDeck } from './HonestyChrome.plain';

import { CAPABILITY } from './capability';
import { useHonesty, type HonestyState, type SealState, type TransportMode } from './honesty';
import styles from './chrome.module.css';

type Provenance =
  | 'db:column'
  | 'db:constraint'
  | 'recomputed'
  | 'staged'
  | 'transport:describe'
  | 'build'
  | 'unset';
type Tone = 'neutral' | 'warn' | 'refuse' | 'ok';

/**
 * One cell's rendering, plus the sentence it owes the reader when the value alone would
 * be read as a verdict it is not.
 */
interface CellReading {
  readonly value: string;
  readonly tone: Tone;
  readonly provenance: Provenance;
  readonly title: string;
  /** Rendered under the strip, verbatim, or null when the value speaks for itself. */
  readonly note: string | null;
}

function Cell({
  label,
  value,
  provenance,
  plain,
  title,
  tone,
}: {
  readonly label: string;
  readonly value: string;
  readonly provenance: Provenance;
  /**
   * One sentence, in the words of somebody who has never read this repository. It is a
   * text node, not a `title`: see the module header on why that distinction is the whole
   * point of this parameter existing.
   *
   * `undefined` until the lazy deck lands, and for ever if it does not. A cell with no
   * sentence declares no description at all — an `aria-describedby` pointing at an element
   * that is not in the document is a broken reference, and `src/a11y/audit.ts` fails it by
   * name (`aria-ref-resolves`). It is also the honest rendering: no sentence is here, so
   * none is announced.
   */
  readonly plain: string | undefined;
  readonly title?: string;
  readonly tone?: Tone;
}): ReactNode {
  const id = useId();
  const labelId = `${id}-label`;
  const plainId = `${id}-plain`;
  const slug = label.replace(/\s+/g, '-');
  return (
    <div
      className={styles.cell}
      data-tone={tone ?? 'neutral'}
      data-provenance={provenance}
      // A stop, not a control. The reader can reach the explanation with the keyboard
      // without the strip acquiring anything that could be pressed.
      role="group"
      tabIndex={0}
      aria-labelledby={labelId}
      {...(plain === undefined ? {} : { 'aria-describedby': plainId })}
      {...(title === undefined ? {} : { title })}
    >
      <span className={styles.label} id={labelId}>
        {label}
      </span>
      <span className={styles.value} data-testid={`chrome-${slug}`}>
        {value}
      </span>
      <span className={styles.provenance} aria-label={`provenance: ${provenance}`}>
        {provenance}
      </span>
      {plain === undefined ? null : (
        <span className={styles.plain} id={plainId} data-testid={`chrome-plain-${slug}`}>
          {plain}
        </span>
      )}
    </div>
  );
}

function transportLabel(mode: TransportMode): { value: string; tone: 'neutral' | 'warn' } {
  if (mode === 'live') return { value: 'LIVE', tone: 'neutral' };
  if (mode === 'replay') return { value: 'REPLAY', tone: 'warn' };
  return { value: 'UNKNOWN', tone: 'warn' };
}

/**
 * The bundle manifest digest, or the reason there is not one.
 *
 * Order matters: a digest that was actually recomputed wins over every explanation,
 * including in LIVE — `EvidenceScreen` opens a bundle over the wire and publishes what it
 * hashed, and a cell that ignored that in favour of a sentence about LIVE would be
 * hiding arithmetic somebody performed.
 */
function bundleReading(honesty: HonestyState): CellReading {
  if (honesty.bundleDigestPrefix !== null) {
    return {
      value: honesty.bundleDigestPrefix,
      tone: 'neutral',
      provenance: 'recomputed',
      title:
        'First 12 hex characters of the SHA-256 over the bundle manifest, recomputed in this ' +
        'browser.',
      note: null,
    };
  }
  if (honesty.transport === 'live') {
    const note =
      'BUNDLE. No bundle byte is on this screen. These bytes came from the live kernel over ' +
      'the wire, so there was no EvidenceBundle to open and none was consulted — which is a ' +
      'different fact from a manifest digest this browser tried to recompute and could not ' +
      'obtain. This cell carries a digest only when a bundle was opened and hashed here.';
    return { value: 'none consulted', tone: 'neutral', provenance: 'unset', title: note, note };
  }
  // REPLAY before the verifier settles, or no transport at all. In both, a bundle digest
  // is a thing this console expects to hold and does not hold yet, which is what the word
  // `unknown` means and the only place it is still the whole answer.
  return {
    value: 'unknown',
    tone: 'neutral',
    provenance: 'unset',
    title:
      'First 12 hex characters of the SHA-256 over the bundle manifest, recomputed in this ' +
      'browser. Nothing has been recomputed yet.',
    note: null,
  };
}

/**
 * The seal.
 *
 * `verified` / `failed` / `verifying` are the verifier's own verdicts and are rendered
 * unchanged. The fourth state is the one that needed words: `unverified` with no detail
 * beside it means NOBODY HAS PUBLISHED A VERDICT, and under LIVE that is not a pending
 * check — it is a check that does not run at all, because the thing it verifies is a
 * bundle and there is no bundle. The classification of a check that ran and could not
 * conclude belongs to `src/verify/`, and this cell renders whatever that reports.
 */
function sealReading(honesty: HonestyState): CellReading {
  const seal: SealState = honesty.seal;
  if (seal === 'verified') {
    return {
      value: 'VERIFIED IN THIS BROWSER',
      tone: 'ok',
      provenance: 'recomputed',
      title: honesty.sealDetail ?? 'The in-browser checks completed and every one held.',
      note: null,
    };
  }
  if (seal === 'failed') {
    return {
      value: 'VERIFICATION FAILED',
      tone: 'refuse',
      provenance: 'recomputed',
      title: honesty.sealDetail ?? 'An in-browser check ran and did not hold.',
      note: null,
    };
  }
  if (seal === 'verifying') {
    return {
      value: 'verifying…',
      tone: 'neutral',
      provenance: 'recomputed',
      title: honesty.sealDetail ?? 'The in-browser checks are running.',
      note: null,
    };
  }
  if (honesty.transport === 'live' && honesty.sealDetail === null) {
    // Not "pending", not "—", and no longer "NOT VERIFIED": the bundle verifier this cell
    // reports is not running and is not going to, so a reader must not be left to decide
    // whether it failed. It is still amber and still `unset`, because nothing was checked.
    const note =
      'SEAL. This cell reports the in-browser BUNDLE verifier, and under a live transport it ' +
      'does not run: there is no bundle to hash, so nothing here has passed and nothing here ' +
      'has failed. Arithmetic is still recomputed on live bytes elsewhere — the custody ' +
      'surface reruns the RFC 6962 inclusion and consistency hashes over the ledger it was ' +
      'served, in this browser, and prints its own verdict there. That verdict, not this ' +
      'cell, is the one to read under LIVE; when custody publishes it, this cell carries it.';
    return { value: 'NOT RUN (no bundle in LIVE)', tone: 'warn', provenance: 'unset', title: note, note };
  }
  // Nothing has been checked, and the reader is told that in the same words they would
  // use to complain about it.
  return {
    value: 'NOT VERIFIED',
    tone: 'warn',
    provenance: 'unset',
    title: honesty.sealDetail ?? 'Nothing has been recomputed in this browser yet.',
    note: null,
  };
}

/**
 * Whether the checkpoint SIGNATURE check can run at all in this build.
 *
 * This is a check that runs on every screen, on arrival, with no network and no payload:
 * `resolveVerifierConfig()` looks for a C2SP log verification key in the compiled build
 * and then in this page's query string, and reports which one it found. The cell states
 * the RESULT OF THAT LOOKUP and nothing further — it is not a verdict about any
 * checkpoint, and it never becomes one, because verifying a signature is
 * `src/verify/checkpoint.ts`'s job and its verdicts appear on the custody surface.
 *
 * `source: 'none'` is the state `.env.demo` ships, and the honest word for it is SKIPPED.
 * `config.sourceNote` is `src/verify/config.ts`'s own sentence and is rendered as it is
 * written there, because the reason a check did not run is not a thing to paraphrase.
 */
function checkpointSignatureReading(config: VerifierConfig): CellReading {
  // `config.sourceNote` is `src/verify/config.ts`'s own sentence in every branch, rendered
  // as that module wrote it. The reason a check did not run is not a thing to paraphrase,
  // and quoting rather than restating also keeps this file's share of the entry chunk to
  // the twenty-two characters of the label.
  const note = `CHECKPOINT SIGNATURE. ${config.sourceNote}`;
  if (config.source === 'none') {
    return {
      value: 'SKIPPED — this build carries no log key',
      tone: 'warn',
      provenance: 'unset',
      title: note,
      note,
    };
  }
  if (config.source === 'build') {
    // An anchor the build pinned. Reported as an ANCHOR, never as a verdict: whether any
    // particular checkpoint signature held is the custody surface's to say.
    return { value: 'anchor: build', tone: 'neutral', provenance: 'build', title: note, note: null };
  }
  // An anchor that arrived with the LINK or was typed in by the reader — usable, and not
  // the same epistemic situation as one the build pinned, so its sentence goes under the
  // strip rather than into a hover.
  return {
    value: `anchor: ${config.source}`,
    tone: 'warn',
    provenance: 'unset',
    title: note,
    note,
  };
}

/**
 * D17 — which capture path this artefact compiled.
 *
 * `unknown` is not a lookup that failed; `honesty.ts` defines it as *no attestation
 * existed when the bundle was built*. That is a statement about the artefact the reader
 * is looking at, and it is true in both transports, so this cell does not branch on the
 * transport at all.
 */
function signaturePathReading(honesty: HonestyState): CellReading {
  if (honesty.signaturePath !== 'unknown') {
    return {
      value: honesty.signaturePath,
      tone: 'neutral',
      provenance: 'build',
      title:
        'Compiled at build time from the GT-15 attestation. WebAuthn is not assumed; if no ' +
        'attestation existed, this says so.',
      note: null,
    };
  }
  const note =
    'SIGNATURE PATH. D17 makes the signature-capture path a build-time selection, read from ' +
    'the GT-15 attestation and compiled in, so that an unverified capability cannot reach a ' +
    'rendered screen. No GT-15 attestation was present when this artefact was built, so it ' +
    'selected NEITHER path — neither WebAuthn nor the OIDC envelope — and no signature can be ' +
    'captured in this build. Printing either name here would assert a capability nobody has ' +
    'verified on the target fleet.';
  return { value: 'none compiled', tone: 'warn', provenance: 'unset', title: note, note };
}

function skewLabel(ms: number | null): string {
  if (ms === null) return 'unknown';
  const sign = ms >= 0 ? '+' : '−';
  return `${sign}${Math.abs(ms)} ms`;
}

/**
 * THE PLAIN SENTENCES, ASKED FOR ONCE.
 *
 * `null` until the lazy deck lands, and `null` for ever if it does not — in which case
 * every cell renders exactly what it renders today minus one explanation, which is a
 * degradation of the copy and not of a single claim. Deliberately silent on failure, for
 * `SurfaceHost`'s reason: a copy module that did not load is not a fact that could not be
 * established, and saying so on the strip would put a console defect where a reader is
 * looking for the provenance of a number.
 */
function usePlainDeck(): PlainDeck | null {
  const [deck, setDeck] = useState<PlainDeck | null>(null);
  useEffect(() => {
    let live = true;
    import('./HonestyChrome.plain').then(
      (module) => {
        if (live) setDeck(module.PLAIN);
      },
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, []);
  return deck;
}

export function HonestyChrome(): ReactNode {
  const honesty = useHonesty();
  // A real lookup, performed on every screen: it reads the key this artefact was compiled
  // with and the one this page's address carries. It touches no network and no payload,
  // which is exactly why it can fill a cell on a screen a reader has just landed on.
  const verifier = useMemo(() => resolveVerifierConfig(), []);
  const plain = usePlainDeck();

  const transport = transportLabel(honesty.transport);
  const bundle = bundleReading(honesty);
  const seal = sealReading(honesty);
  const checkpointSignature = checkpointSignatureReading(verifier);
  const signaturePath = signaturePathReading(honesty);

  const notes: readonly { readonly id: string; readonly text: string }[] = [
    { id: 'bundle', text: bundle.note },
    { id: 'seal', text: seal.note },
    { id: 'checkpoint-signature', text: checkpointSignature.note },
    { id: 'signature-path', text: signaturePath.note },
  ].flatMap((entry) => (entry.text === null ? [] : [{ id: entry.id, text: entry.text }]));

  return (
    <aside className={styles.chrome} aria-label="Honesty chrome" data-testid="honesty-chrome">
      <div className={styles.row}>
        <Cell
          label="transport"
          value={transport.value}
          tone={transport.tone}
          // Read off `transport.describe().mode` by the composition root — the object that
          // holds the bytes, not a flag beside it. `unset` only where no transport has
          // declared itself, which is the one state nothing established.
          provenance={honesty.transport === 'unknown' ? 'unset' : 'transport:describe'}
          plain={plain?.transport}
          title={
            honesty.transport === 'replay'
              ? 'These bytes came from a signed EvidenceBundle captured from a real run, and were verified before being rendered. The word REPLAY is read from describe() on the transport that served them.'
              : honesty.transport === 'live'
                ? 'These bytes came from a live kernel over the wire. The word LIVE is read from describe() on the transport that served them, never from a build-time flag.'
                : 'No transport has declared itself. Nothing on screen has a stated origin.'
          }
        />
        <Cell
          label="bundle"
          value={bundle.value}
          tone={bundle.tone}
          provenance={bundle.provenance}
          plain={plain?.bundle}
          title={bundle.title}
        />
        <Cell
          label="seal"
          value={seal.value}
          tone={seal.tone}
          provenance={seal.provenance}
          plain={plain?.seal}
          title={seal.title}
        />
        <Cell
          label="checkpoint signature"
          value={checkpointSignature.value}
          tone={checkpointSignature.tone}
          provenance={checkpointSignature.provenance}
          plain={plain?.['checkpoint-signature']}
          title={checkpointSignature.title}
        />
        <Cell
          label="corpus root"
          value={honesty.corpusRoot ?? 'unknown'}
          provenance={honesty.corpusRoot === null ? 'unset' : 'db:column'}
          plain={plain?.['corpus-root']}
          title="The commit the displayed blame closure was computed against."
        />
        <Cell
          label="clock skew"
          value={skewLabel(honesty.clockSkewMs)}
          provenance={honesty.clockSkewMs === null ? 'unset' : 'recomputed'}
          plain={plain?.['clock-skew']}
          title="Server instant minus this browser's instant. A screenshot's timestamp means nothing without it."
        />
        <Cell
          label="signature path"
          value={signaturePath.value}
          tone={signaturePath.tone}
          provenance={signaturePath.provenance}
          plain={plain?.['signature-path']}
          title={signaturePath.title}
        />
        <Cell
          label="render"
          value={CAPABILITY.renderMode === '3d' ? 'walk (3D)' : 'ribbon (2D)'}
          provenance="build"
          plain={plain?.render}
          title={CAPABILITY.reasons.join(' ')}
        />
        <Cell
          label="build"
          value={honesty.buildId}
          provenance="build"
          plain={plain?.build}
        />
      </div>
      {notes.map((note) => (
        <p key={note.id} className={styles.detail} data-testid={`honesty-note-${note.id}`}>
          {note.text}
        </p>
      ))}
      {honesty.sealDetail !== null && (
        <p className={styles.detail} data-testid="honesty-seal-detail">
          {honesty.sealDetail}
        </p>
      )}
    </aside>
  );
}
