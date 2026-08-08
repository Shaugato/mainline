// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Generates `src/data/types.generated.ts` from `contracts/*.schema.json`.
 *
 * Run with `node scripts/gen-types.ts` (Node 24 strips the types; no bundler, no
 * dependency). `--check` regenerates in memory and exits non-zero if the committed file
 * differs, which is how CI proves the contracts and the types have not drifted apart.
 *
 * Three properties, and each of them is why this exists instead of a library:
 *
 *   1. **No `any`, ever.** An unconstrained schema position becomes `unknown`, which
 *      forces a call site to narrow. `any` in a read model for a safety gate is a
 *      silent licence to read a field that is not there.
 *   2. **No anonymous index signatures.** The generated model is a closed set of named
 *      fields. The two places an open map is unavoidable — `ext` and the authority-gap
 *      `key` in the SPECIFICATION-owned refusal contract, which this repository may not
 *      edit — go through the single named alias `StringMap<T>`, so an audit can find
 *      every one of them by grepping for one word.
 *   3. **A name collision is an ERROR, not a silent rename.** Two `$defs` that would
 *      produce the same TypeScript name are disambiguated by document prefix, and the
 *      run PRINTS every disambiguation it made. A third collision fails the run.
 *
 * `if`/`then`/`else`, `pattern`, `format`, `minimum` and the other refinement keywords
 * do not appear in the output. They are not expressible in TypeScript's type system,
 * they ARE enforced at runtime by `src/data/schema.ts` against these same files, and a
 * generated type that quietly dropped them without saying so would be the console
 * claiming a guarantee the compiler is not giving it.
 */

import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const CONTRACTS = join(ROOT, 'contracts');
const OUTPUT = join(ROOT, 'src', 'data', 'types.generated.ts');

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
type SchemaObject = Record<string, Json>;

interface Document {
  readonly file: string;
  readonly id: string;
  readonly short: string;
  readonly schema: SchemaObject;
}

/** file base name → the exported name of that document's ROOT type. `null` = emit none. */
const ROOT_NAMES = new Map<string, string | null>([
  ['common', null],
  ['envelope', 'ReadEnvelope'],
  ['permit', 'PermitResponse'],
  ['change-request', 'ChangeRequestResponse'],
  ['blocking-check', 'BlockingChecksResponse'],
  ['disposition', 'DispositionResponse'],
  ['exposure', 'ExposureResponse'],
  ['clause', 'ClauseResponse'],
  ['ancestry', 'AncestryResponse'],
  ['ledger', 'LedgerResponse'],
  ['silence', 'SilenceResponse'],
  ['recall-run', 'RecallRunResponse'],
  ['propagation', 'PropagationResponse'],
  ['audit', 'AuditResponse'],
  ['invoke', 'InvokeResponse'],
  ['bundle', 'EvidenceBundleManifest'],
  ['refusal', 'RefusalPayload'],
]);

/**
 * Hand-pinned names where the mechanical one would shadow a DOM global or read badly.
 * Keyed by `<file>#<json-pointer>`.
 */
const NAME_OVERRIDES = new Map<string, string>([
  ['ledger.schema.json#/$defs/node', 'LedgerNode'],
  ['ledger.schema.json#/$defs/leaf', 'LedgerLeaf'],
  ['ledger.schema.json#/$defs/checkpoint', 'LedgerCheckpoint'],
  ['ledger.schema.json#/$defs/cosignature', 'LedgerCosignature'],
  ['bundle.schema.json#/$defs/frame', 'EvidenceBundleFrame'],
  ['refusal.schema.json#/$defs/uuid', 'RefusalUuid'],
  ['refusal.schema.json#/$defs/digest', 'RefusalDigest'],
]);

// ── Loading ────────────────────────────────────────────────────────────────

function isObject(value: Json | undefined): value is SchemaObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function loadDocuments(): Document[] {
  const files = readdirSync(CONTRACTS)
    .filter((name) => name.endsWith('.schema.json'))
    .sort();
  return files.map((file) => {
    const text = readFileSync(join(CONTRACTS, file), 'utf8');
    const schema = JSON.parse(text) as SchemaObject;
    const id = schema['$id'];
    if (typeof id !== 'string') {
      throw new Error(`contracts/${file} declares no $id.`);
    }
    return { file, id, short: file.replace(/\.schema\.json$/, ''), schema };
  });
}

// ── Naming ─────────────────────────────────────────────────────────────────

function pascal(text: string): string {
  return text
    .split(/[^A-Za-z0-9]+/)
    .filter((part) => part !== '')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('');
}

interface NameTable {
  /** `<$id>#<pointer>` → exported TypeScript name. */
  readonly byRef: Map<string, string>;
  readonly disambiguated: string[];
}

function buildNames(documents: readonly Document[]): NameTable {
  const byRef = new Map<string, string>();
  const used = new Map<string, string>();
  const disambiguated: string[] = [];

  const claim = (key: string, preferred: string, docShort: string, what: string): void => {
    const override = NAME_OVERRIDES.get(key.replace(/^[^#]*#/, `${docShort}.schema.json#`));
    let name = override ?? preferred;
    const owner = used.get(name);
    if (owner !== undefined && owner !== key) {
      const alternative = `${pascal(docShort)}${preferred}`;
      const altOwner = used.get(alternative);
      if (altOwner !== undefined && altOwner !== key) {
        throw new Error(
          `gen-types: cannot name ${what}. "${name}" is taken by ${owner} and the fallback ` +
            `"${alternative}" is taken by ${altOwner}. Add an entry to NAME_OVERRIDES.`,
        );
      }
      disambiguated.push(`${what} → ${alternative} (because "${name}" was taken by ${owner})`);
      name = alternative;
    }
    used.set(name, key);
    byRef.set(key, name);
  };

  for (const document of documents) {
    const rootName = ROOT_NAMES.get(document.short);
    if (rootName === undefined) {
      throw new Error(
        `gen-types: contracts/${document.file} has no entry in ROOT_NAMES. Every contract must ` +
          'declare the exported name of its root type, or declare null to emit none.',
      );
    }
    if (rootName !== null) {
      claim(`${document.id}#`, rootName, document.short, `${document.file} (root)`);
    }
    const defs = document.schema['$defs'];
    if (!isObject(defs)) continue;
    for (const defName of Object.keys(defs)) {
      claim(
        `${document.id}#/$defs/${defName}`,
        pascal(defName),
        document.short,
        `${document.file}#/$defs/${defName}`,
      );
    }
  }

  return { byRef, disambiguated };
}

// ── Rendering ──────────────────────────────────────────────────────────────

interface Context {
  readonly documents: readonly Document[];
  readonly byId: Map<string, Document>;
  readonly names: Map<string, string>;
  readonly baseId: string;
}

function resolveRefKey(ref: string, baseId: string): string {
  const hash = ref.indexOf('#');
  const uri = hash === -1 ? ref : ref.slice(0, hash);
  const fragment = hash === -1 ? '' : ref.slice(hash + 1);
  const target = uri === '' ? baseId : new URL(uri, baseId).toString();
  return `${target}#${fragment}`;
}

function literal(value: Json): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  // A const/enum member that is a container is legal JSON Schema and does not occur in
  // these contracts. Rendering it as `unknown` would be a silent widening, so refuse.
  throw new Error(`gen-types: const/enum member ${JSON.stringify(value)} is not a scalar.`);
}

function primitive(name: string): string {
  switch (name) {
    case 'string':
      return 'string';
    case 'integer':
    case 'number':
      return 'number';
    case 'boolean':
      return 'boolean';
    case 'null':
      return 'null';
    case 'array':
      return 'readonly JsonValue[]';
    case 'object':
      return 'JsonObject';
    default:
      throw new Error(`gen-types: unknown JSON Schema type "${name}".`);
  }
}

/**
 * A rendered fragment needs bracketing only when it is a bare union or intersection at
 * the top level. An object literal or a tuple is already self-delimiting, and wrapping
 * one in parentheses produces `ReadEnvelope & ({ … })`, which is correct but reads like
 * a generator that does not know what it emitted.
 */
function selfDelimiting(part: string): boolean {
  return part.startsWith('{') || part.startsWith('readonly [') || !/[|&]/.test(part);
}

function union(parts: readonly string[]): string {
  const unique = [...new Set(parts)];
  if (unique.length === 0) return 'unknown';
  if (unique.length === 1) return unique[0] ?? 'unknown';
  return unique.map((part) => (selfDelimiting(part) ? part : `(${part})`)).join(' | ');
}

function intersect(parts: readonly string[]): string {
  const unique = [...new Set(parts)].filter((part) => part !== 'unknown');
  if (unique.length === 0) return 'unknown';
  if (unique.length === 1) return unique[0] ?? 'unknown';
  return unique.map((part) => (selfDelimiting(part) ? part : `(${part})`)).join(' & ');
}

function isIdentifier(name: string): boolean {
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name);
}

function hasApplicator(schema: SchemaObject): boolean {
  return (
    Array.isArray(schema['oneOf']) || Array.isArray(schema['anyOf']) || Array.isArray(schema['allOf'])
  );
}

function renderObject(schema: SchemaObject, ctx: Context, indent: string): string {
  const properties = schema['properties'];
  const required = Array.isArray(schema['required'])
    ? new Set((schema['required']).filter((v): v is string => typeof v === 'string'))
    : new Set<string>();
  const additional = schema['additionalProperties'];

  const parts: string[] = [];

  if (isObject(properties)) {
    const inner = indent + '  ';
    const lines: string[] = [];
    for (const [name, sub] of Object.entries(properties)) {
      const rendered = render(sub, ctx, inner);
      const optional = required.has(name) ? '' : '?';
      const key = isIdentifier(name) ? name : JSON.stringify(name);
      const description = isObject(sub) && typeof sub['description'] === 'string' ? sub['description'] : null;
      if (description !== null) {
        lines.push(`${inner}/** ${description.replace(/\*\//g, '*\\/')} */`);
      }
      lines.push(`${inner}readonly ${key}${optional}: ${rendered};`);
    }
    parts.push(lines.length === 0 ? '{}' : `{\n${lines.join('\n')}\n${indent}}`);
  }

  if (additional !== undefined && additional !== false) {
    const valueType = additional === true ? 'JsonValue' : render(additional, ctx, indent);
    parts.push(`StringMap<${valueType}>`);
  } else if (!isObject(properties) && !hasApplicator(schema)) {
    // `{"type": "object"}` with nothing else: an object whose shape the contract does
    // not constrain. `JsonObject` says exactly that, and forces narrowing.
    //
    // When an applicator IS present — `{"type":"object","required":["kind"],"oneOf":[…]}`,
    // the shape every tagged union in the refusal contract uses — emitting JsonObject
    // as well would intersect an index signature onto each variant and quietly make
    // `atom.anything` legal. The variants already say what the object is.
    parts.push('JsonObject');
  }

  return intersect(parts);
}

function render(schema: Json, ctx: Context, indent: string): string {
  if (schema === true) return 'JsonValue';
  if (schema === false) return 'never';
  if (!isObject(schema)) {
    throw new Error(`gen-types: a schema must be an object or a boolean, got ${JSON.stringify(schema)}.`);
  }

  const constValue = schema['const'];
  if (constValue !== undefined) return literal(constValue);

  const enumValues = schema['enum'];
  if (Array.isArray(enumValues)) return union(enumValues.map(literal));

  const parts: string[] = [];

  const ref = schema['$ref'];
  if (typeof ref === 'string') {
    const key = resolveRefKey(ref, ctx.baseId);
    const name = ctx.names.get(key);
    if (name === undefined) {
      throw new Error(`gen-types: $ref "${ref}" (from ${ctx.baseId}) resolves to ${key}, which has no name.`);
    }
    parts.push(name);
  }

  const typeKeyword = schema['type'];
  if (typeKeyword !== undefined) {
    const names = (Array.isArray(typeKeyword) ? typeKeyword : [typeKeyword]) as string[];
    const rendered = names.map((name) => {
      if (name === 'object') return renderObject(schema, ctx, indent);
      if (name === 'array') return renderArray(schema, ctx, indent);
      return primitive(name);
    });
    parts.push(union(rendered));
  } else if (isObject(schema['properties']) || schema['additionalProperties'] !== undefined) {
    parts.push(renderObject(schema, ctx, indent));
  } else if (schema['items'] !== undefined || Array.isArray(schema['prefixItems'])) {
    parts.push(renderArray(schema, ctx, indent));
  }

  const allOf = schema['allOf'];
  if (Array.isArray(allOf)) {
    parts.push(intersect(allOf.map((sub) => render(sub, ctx, indent))));
  }

  const oneOf = schema['oneOf'];
  if (Array.isArray(oneOf)) {
    parts.push(union(oneOf.map((sub) => render(sub, ctx, indent))));
  }

  const anyOf = schema['anyOf'];
  if (Array.isArray(anyOf)) {
    parts.push(union(anyOf.map((sub) => render(sub, ctx, indent))));
  }

  return intersect(parts);
}

function renderArray(schema: SchemaObject, ctx: Context, indent: string): string {
  const prefixItems = schema['prefixItems'];
  if (Array.isArray(prefixItems)) {
    const tuple = prefixItems.map((sub) => render(sub, ctx, indent)).join(', ');
    return `readonly [${tuple}]`;
  }
  const items = schema['items'];
  if (items === undefined) return 'readonly JsonValue[]';
  const rendered = render(items, ctx, indent);
  const needsParens = rendered.includes('|') || rendered.includes('&') || rendered.includes('{');
  return needsParens ? `readonly (${rendered})[]` : `readonly ${rendered}[]`;
}

// ── Emission ───────────────────────────────────────────────────────────────

const PREAMBLE = `// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT.
 *
 * Produced by \`node scripts/gen-types.ts\` from \`contracts/*.schema.json\`.
 * Regenerate after any contract change; \`node scripts/gen-types.ts --check\` fails CI
 * when this file and the contracts have drifted apart.
 *
 * What these types DO carry: the field names, their nullability, whether they are
 * optional, and every closed vocabulary in the read model as a literal union.
 *
 * What they do NOT carry, and cannot: \`pattern\`, \`format\`, \`minimum\`, \`maxItems\`,
 * \`if\`/\`then\`/\`else\` and the rest of the refinement keywords. Those are enforced at
 * RUNTIME by \`src/data/schema.ts\` against the same contract files, on every payload,
 * before a surface sees it. A type here is a shape, not a guarantee — the guarantee is
 * the validation the transport performs, and no code in this console may treat a
 * successful compile as evidence that a payload was well formed.
 */

/** A JSON value, for positions a contract deliberately leaves open. Never \`any\`. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

/** A JSON object whose members a contract does not constrain. */
export type JsonObject = { readonly [key: string]: JsonValue };

/**
 * The ONE open-map alias in the generated read model.
 *
 * It appears only where a schema declares \`additionalProperties\` without \`properties\`,
 * which in this repository happens only inside the specification-owned refusal contract
 * (\`ext\` and the authority-gap \`key\`). Everything else is a closed set of named fields.
 * Grep for \`StringMap\` to find every open position in the model.
 */
export type StringMap<T> = { readonly [key: string]: T };
`;

function emit(documents: readonly Document[], names: NameTable): string {
  const byId = new Map(documents.map((document) => [document.id, document]));
  const blocks: string[] = [];

  for (const document of documents) {
    const ctx: Context = { documents, byId, names: names.byRef, baseId: document.id };
    const sectionLines: string[] = [];

    const title = typeof document.schema['title'] === 'string' ? document.schema['title'] : document.file;
    sectionLines.push(
      `// ${'─'.repeat(74)}\n// ${document.file} — ${title}\n// ${'─'.repeat(74)}`,
    );

    const rootName = names.byRef.get(`${document.id}#`);
    if (rootName !== undefined) {
      const description =
        typeof document.schema['description'] === 'string' ? document.schema['description'] : null;
      if (description !== null) sectionLines.push(`/**\n * ${wrap(description, 92, ' * ')}\n */`);
      sectionLines.push(`export type ${rootName} = ${render(document.schema, ctx, '')};`);
    }

    const defs = document.schema['$defs'];
    if (isObject(defs)) {
      for (const [defName, sub] of Object.entries(defs)) {
        const name = names.byRef.get(`${document.id}#/$defs/${defName}`);
        if (name === undefined) continue;
        const description = isObject(sub) && typeof sub['description'] === 'string' ? sub['description'] : null;
        if (description !== null) sectionLines.push(`/**\n * ${wrap(description, 92, ' * ')}\n */`);
        sectionLines.push(`export type ${name} = ${render(sub, ctx, '')};`);
      }
    }

    blocks.push(sectionLines.join('\n\n'));
  }

  return `${PREAMBLE}\n${blocks.join('\n\n')}\n`;
}

function wrap(text: string, width: number, continuation: string): string {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    if (current === '') current = word;
    else if (current.length + 1 + word.length <= width) current = `${current} ${word}`;
    else {
      lines.push(current);
      current = word;
    }
  }
  if (current !== '') lines.push(current);
  return lines.join(`\n${continuation}`);
}

// ── Run ────────────────────────────────────────────────────────────────────

const documents = loadDocuments();
const names = buildNames(documents);
const output = emit(documents, names);

const check = process.argv.includes('--check');

if (names.disambiguated.length > 0) {
  process.stdout.write('gen-types: disambiguated names\n');
  for (const line of names.disambiguated) process.stdout.write(`  ${line}\n`);
}

if (check) {
  let existing = '';
  try {
    existing = readFileSync(OUTPUT, 'utf8');
  } catch {
    process.stderr.write('gen-types --check: src/data/types.generated.ts does not exist.\n');
    process.exit(1);
  }
  if (existing.replace(/\r\n/g, '\n') !== output) {
    process.stderr.write(
      'gen-types --check: src/data/types.generated.ts is out of date with contracts/.\n' +
        '  Run `node scripts/gen-types.ts` and commit the result.\n',
    );
    process.exit(1);
  }
  process.stdout.write(`gen-types --check: types.generated.ts matches ${documents.length} contract(s).\n`);
} else {
  writeFileSync(OUTPUT, output, 'utf8');
  process.stdout.write(
    `gen-types: wrote src/data/types.generated.ts from ${documents.length} contract(s), ` +
      `${names.byRef.size} exported type(s).\n`,
  );
}
