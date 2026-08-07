// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * A JSON Schema draft 2020-12 validator, restricted to the subset this repository's
 * contracts actually use — and REFUSING every keyword outside it.
 *
 * D2 forbids a validation library: in a repository where the dependency graph is a
 * licence and liability boundary, a 200 KB schema compiler for fifteen hand-authored
 * contracts is an audit nobody needs. But a hand-rolled validator has a failure mode a
 * library does not, and it is fatal to this domain: a validator that silently ignores a
 * keyword it never implemented turns every conformance test green while asserting
 * nothing at all. PL-2 cannot survive that, so:
 *
 *   **An unknown or unimplemented keyword is a COMPILE ERROR, not an ignored annotation.**
 *
 * `compileSchema` walks the whole schema document eagerly and throws on the first
 * keyword outside `KNOWN_KEYWORDS`. A contract author who reaches for
 * `unevaluatedProperties` gets a loud failure at compile time rather than a quiet pass
 * at validation time. That inversion is the entire reason this file is defensible.
 *
 * Deviations from the specification, stated rather than hidden:
 *
 *   1. `format` is an ASSERTION here, not an annotation. Draft 2020-12 makes format
 *      annotation-only unless the format-assertion vocabulary is in play. Treating
 *      `"format": "date-time"` as decoration in a contract that uses it to mean
 *      "RFC 3339 instant" would be the silent-ignore failure wearing a specification
 *      citation, so formats are checked — and an UNKNOWN format name is a compile error.
 *   2. `$dynamicRef`, `$dynamicAnchor`, `$anchor`, `$vocabulary`, `unevaluatedProperties`
 *      and `unevaluatedItems` are not implemented and are refused at compile time.
 *   3. `$ref` siblings ARE honoured (2020-12 semantics): `{"$ref": ..., "description": ...}`
 *      validates against both.
 *   4. Numeric `multipleOf` uses floating-point remainder and is therefore approximate
 *      for non-representable decimals. No contract in this repository uses it; it is
 *      implemented so that a future one fails loudly on precision rather than silently.
 */

// ── Public shapes ──────────────────────────────────────────────────────────

export interface ValidationError {
  /** RFC 6901 JSON Pointer into the instance. */
  readonly instancePath: string;
  /** RFC 6901 JSON Pointer into the schema document, prefixed by the document's $id. */
  readonly schemaPath: string;
  /** The keyword that failed. */
  readonly keyword: string;
  /** Written for the person who has to fix the payload, because that is who reads it. */
  readonly message: string;
}

export interface ValidationResult {
  readonly valid: boolean;
  readonly errors: readonly ValidationError[];
}

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

/** A schema document, as parsed from a `*.schema.json` file. */
export type SchemaDocument = { readonly [key: string]: JsonValue };

// ── The closed keyword set ─────────────────────────────────────────────────

/**
 * Every keyword this validator implements. A schema containing anything else is
 * refused at compile time.
 *
 * `$schema`, `$id`, `$comment`, `title`, `description`, `default` and `examples` are
 * annotations: known, carried, and asserted by nothing.
 */
const ANNOTATION_KEYWORDS = new Set([
  '$schema',
  '$id',
  '$comment',
  'title',
  'description',
  'default',
  'examples',
  'deprecated',
  'readOnly',
  'writeOnly',
  '$defs',
]);

const ASSERTION_KEYWORDS = new Set([
  '$ref',
  'allOf',
  'anyOf',
  'oneOf',
  'not',
  'if',
  'then',
  'else',
  'properties',
  'patternProperties',
  'additionalProperties',
  'propertyNames',
  'dependentRequired',
  'dependentSchemas',
  'items',
  'prefixItems',
  'contains',
  'minContains',
  'maxContains',
  'type',
  'enum',
  'const',
  'multipleOf',
  'maximum',
  'exclusiveMaximum',
  'minimum',
  'exclusiveMinimum',
  'maxLength',
  'minLength',
  'pattern',
  'maxItems',
  'minItems',
  'uniqueItems',
  'maxProperties',
  'minProperties',
  'required',
  'format',
]);

const KNOWN_KEYWORDS = new Set([...ANNOTATION_KEYWORDS, ...ASSERTION_KEYWORDS]);

const SIMPLE_TYPES = new Set([
  'null',
  'boolean',
  'object',
  'array',
  'number',
  'string',
  'integer',
]);

// ── Formats, asserted ──────────────────────────────────────────────────────

/**
 * RFC 3339 §5.6 `date-time`. Deliberately strict: a trailing `Z` or a numeric offset,
 * a real calendar date, and a real clock time. `2026-02-30T00:00:00Z` is refused,
 * because a contract that accepts an impossible date has not checked the date.
 */
const DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/;

function isRealDateTime(value: string): boolean {
  const m = DATE_TIME.exec(value);
  if (m === null) return false;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const hour = Number(m[4]);
  const minute = Number(m[5]);
  const second = Number(m[6]);
  if (month < 1 || month > 12) return false;
  if (hour > 23 || minute > 59) return false;
  // 60 is a legal leap second in RFC 3339.
  if (second > 60) return false;
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return day >= 1 && day <= daysInMonth;
}

const FORMATS: Record<string, (value: string) => boolean> = {
  'date-time': isRealDateTime,
  uuid: (v) => /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(v),
  uri: (v) => /^[A-Za-z][A-Za-z0-9+.-]*:/.test(v),
  regex: (v) => {
    try {
      new RegExp(v, 'u');
      return true;
    } catch {
      return false;
    }
  },
};

// ── Compilation ────────────────────────────────────────────────────────────

export class SchemaCompileError extends Error {
  readonly schemaPath: string;

  constructor(schemaPath: string, message: string) {
    super(`${schemaPath}: ${message}`);
    this.name = 'SchemaCompileError';
    this.schemaPath = schemaPath;
  }
}

export class SchemaRefError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SchemaRefError';
  }
}

function isPlainObject(value: unknown): value is Record<string, JsonValue> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** RFC 6901 escaping, for the pointers in error messages. */
function pointerSegment(segment: string): string {
  return segment.replace(/~/g, '~0').replace(/\//g, '~1');
}

/**
 * A registry of schema documents keyed by `$id`. Cross-document `$ref`s resolve
 * through it; a reference to a document nobody registered is an error, never a pass.
 */
export class SchemaRegistry {
  private readonly documents = new Map<string, SchemaDocument>();

  add(document: SchemaDocument): this {
    const id = document['$id'];
    if (typeof id !== 'string' || id === '') {
      throw new SchemaCompileError('<anonymous>', 'a registered schema document must declare a string $id.');
    }
    const existing = this.documents.get(id);
    if (existing !== undefined && existing !== document) {
      throw new SchemaCompileError(id, 'two different documents claim this $id.');
    }
    this.documents.set(id, document);
    return this;
  }

  get(id: string): SchemaDocument | undefined {
    return this.documents.get(id);
  }

  ids(): readonly string[] {
    return [...this.documents.keys()].sort();
  }

  /**
   * Walks every registered document and refuses any unknown keyword. Call this once,
   * at startup and in CI, so that an unimplementable contract cannot reach a test run
   * disguised as a passing one.
   */
  compileAll(): void {
    for (const [id, document] of this.documents) {
      walkSchema(document, id, '#');
    }
    // A $ref that names nothing is worse than an unknown keyword: it validates
    // vacuously. Resolve every reference now.
    for (const [id, document] of this.documents) {
      for (const ref of collectRefs(document)) {
        this.resolve(ref, id);
      }
    }
  }

  /**
   * Resolves a `$ref` against a base document `$id`.
   *
   * Supported forms: `#`, `#/a/b`, `other.schema.json`, `other.schema.json#/$defs/x`,
   * and an absolute `https://…#/$defs/x`. Relative references resolve against the base
   * document's `$id` using the URL algorithm, which is what the `$id` values in
   * `contracts/` are shaped for.
   */
  resolve(ref: string, baseId: string): { document: SchemaDocument; schema: JsonValue; path: string } {
    const hashIndex = ref.indexOf('#');
    const uriPart = hashIndex === -1 ? ref : ref.slice(0, hashIndex);
    const fragment = hashIndex === -1 ? '' : ref.slice(hashIndex + 1);

    let targetId = baseId;
    if (uriPart !== '') {
      try {
        targetId = new URL(uriPart, baseId).toString();
      } catch {
        throw new SchemaRefError(`${baseId}: $ref "${ref}" is not resolvable against the base $id.`);
      }
    }

    const document = this.documents.get(targetId);
    if (document === undefined) {
      throw new SchemaRefError(
        `${baseId}: $ref "${ref}" names schema document "${targetId}", which is not registered. ` +
          `Registered: ${this.ids().join(', ') || '(none)'}.`,
      );
    }

    if (fragment === '') {
      return { document, schema: document as JsonValue, path: `${targetId}#` };
    }
    if (!fragment.startsWith('/')) {
      throw new SchemaRefError(
        `${baseId}: $ref "${ref}" uses a plain-name fragment. $anchor is not implemented; use a JSON Pointer.`,
      );
    }
    const schema = resolvePointer(document as JsonValue, fragment);
    if (schema === undefined) {
      throw new SchemaRefError(`${baseId}: $ref "${ref}" points at "${fragment}", which does not exist in ${targetId}.`);
    }
    return { document, schema, path: `${targetId}#${fragment}` };
  }

  /** Validates an instance against a registered document, optionally at a pointer. */
  validate(schemaId: string, instance: unknown, pointer = ''): ValidationResult {
    const document = this.documents.get(schemaId);
    if (document === undefined) {
      throw new SchemaRefError(`no schema document registered under "${schemaId}".`);
    }
    const schema = pointer === '' ? (document as JsonValue) : resolvePointer(document as JsonValue, pointer);
    if (schema === undefined) {
      throw new SchemaRefError(`"${pointer}" does not exist in ${schemaId}.`);
    }
    const errors: ValidationError[] = [];
    validateNode(this, schema, instance as JsonValue, {
      baseId: schemaId,
      instancePath: '',
      schemaPath: `${schemaId}#${pointer}`,
      errors,
    });
    return { valid: errors.length === 0, errors };
  }
}

export function resolvePointer(root: JsonValue, pointer: string): JsonValue | undefined {
  if (pointer === '') return root;
  let current: JsonValue | undefined = root;
  for (const rawSegment of pointer.slice(1).split('/')) {
    if (current === undefined) return undefined;
    const segment = rawSegment.replace(/~1/g, '/').replace(/~0/g, '~');
    if (Array.isArray(current)) {
      const index = Number(segment);
      if (!Number.isInteger(index) || index < 0 || index >= current.length) return undefined;
      current = current[index];
    } else if (isPlainObject(current)) {
      if (!Object.hasOwn(current, segment)) return undefined;
      current = current[segment];
    } else {
      return undefined;
    }
  }
  return current;
}

/** Eagerly refuses unknown keywords, bad `type` values and unknown formats. */
function walkSchema(schema: JsonValue, documentId: string, path: string): void {
  if (typeof schema === 'boolean') return;
  if (!isPlainObject(schema)) {
    throw new SchemaCompileError(`${documentId}${path}`, 'a schema must be an object or a boolean.');
  }

  for (const [keyword, value] of Object.entries(schema)) {
    if (!KNOWN_KEYWORDS.has(keyword)) {
      throw new SchemaCompileError(
        `${documentId}${path}`,
        `keyword "${keyword}" is not implemented by this validator. ` +
          'Silently ignoring it would make every test that uses this contract assert less than it claims, ' +
          'so it is refused. Implement it in src/data/schema.ts or restate the constraint with an implemented keyword.',
      );
    }

    const childPath = `${path}/${pointerSegment(keyword)}`;

    switch (keyword) {
      case 'type': {
        const names = Array.isArray(value) ? value : [value];
        for (const name of names) {
          if (typeof name !== 'string' || !SIMPLE_TYPES.has(name)) {
            throw new SchemaCompileError(`${documentId}${childPath}`, `"${String(name)}" is not a JSON Schema type.`);
          }
        }
        break;
      }
      case 'format': {
        if (typeof value !== 'string' || !Object.hasOwn(FORMATS, value)) {
          throw new SchemaCompileError(
            `${documentId}${childPath}`,
            `format "${String(value)}" is not implemented. This validator asserts formats rather than ` +
              'annotating them, so an unknown one is refused instead of quietly passing.',
          );
        }
        break;
      }
      case 'pattern': {
        if (typeof value !== 'string') {
          throw new SchemaCompileError(`${documentId}${childPath}`, 'pattern must be a string.');
        }
        try {
          new RegExp(value, 'u');
        } catch (error) {
          throw new SchemaCompileError(
            `${documentId}${childPath}`,
            `pattern is not a valid ECMA-262 regular expression: ${String(error)}`,
          );
        }
        break;
      }
      case 'required': {
        if (!Array.isArray(value) || value.some((v) => typeof v !== 'string')) {
          throw new SchemaCompileError(`${documentId}${childPath}`, 'required must be an array of strings.');
        }
        break;
      }
      case 'properties':
      case 'patternProperties':
      case 'dependentSchemas':
      case '$defs': {
        if (!isPlainObject(value)) {
          throw new SchemaCompileError(`${documentId}${childPath}`, `${keyword} must be an object.`);
        }
        for (const [name, sub] of Object.entries(value)) {
          walkSchema(sub, documentId, `${childPath}/${pointerSegment(name)}`);
        }
        break;
      }
      case 'allOf':
      case 'anyOf':
      case 'oneOf':
      case 'prefixItems': {
        if (!Array.isArray(value)) {
          throw new SchemaCompileError(`${documentId}${childPath}`, `${keyword} must be an array of schemas.`);
        }
        value.forEach((sub, index) => walkSchema(sub, documentId, `${childPath}/${index}`));
        break;
      }
      case 'not':
      case 'if':
      case 'then':
      case 'else':
      case 'items':
      case 'contains':
      case 'propertyNames':
      case 'additionalProperties': {
        walkSchema(value, documentId, childPath);
        break;
      }
      default:
        break;
    }
  }
}

function collectRefs(schema: JsonValue, found: string[] = []): readonly string[] {
  if (Array.isArray(schema)) {
    for (const item of schema) collectRefs(item, found);
    return found;
  }
  if (!isPlainObject(schema)) return found;
  const ref = schema['$ref'];
  if (typeof ref === 'string') found.push(ref);
  for (const [key, value] of Object.entries(schema)) {
    if (key === '$ref') continue;
    collectRefs(value, found);
  }
  return found;
}

// ── Validation ─────────────────────────────────────────────────────────────

interface Context {
  readonly baseId: string;
  readonly instancePath: string;
  readonly schemaPath: string;
  readonly errors: ValidationError[];
}

function fail(ctx: Context, keyword: string, message: string): void {
  ctx.errors.push({
    instancePath: ctx.instancePath === '' ? '/' : ctx.instancePath,
    schemaPath: `${ctx.schemaPath}/${keyword}`,
    keyword,
    message,
  });
}

function child(ctx: Context, instanceSegment: string | null, schemaSegments: string): Context {
  return {
    baseId: ctx.baseId,
    instancePath:
      instanceSegment === null ? ctx.instancePath : `${ctx.instancePath}/${pointerSegment(instanceSegment)}`,
    schemaPath: `${ctx.schemaPath}${schemaSegments}`,
    errors: ctx.errors,
  };
}

function branch(ctx: Context, schemaSegments: string): { ctx: Context; errors: ValidationError[] } {
  const errors: ValidationError[] = [];
  return {
    ctx: {
      baseId: ctx.baseId,
      instancePath: ctx.instancePath,
      schemaPath: `${ctx.schemaPath}${schemaSegments}`,
      errors,
    },
    errors,
  };
}

function typeOf(value: JsonValue): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number';
  return typeof value;
}

function matchesType(value: JsonValue, name: string): boolean {
  const actual = typeOf(value);
  if (name === 'number') return actual === 'number' || actual === 'integer';
  return actual === name;
}

/** Structural equality over JSON values, for `const`, `enum` and `uniqueItems`. */
export function jsonEqual(a: JsonValue, b: JsonValue): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, index) => jsonEqual(item, b[index] as JsonValue));
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const aKeys = Object.keys(a).sort();
    const bKeys = Object.keys(b).sort();
    if (aKeys.length !== bKeys.length) return false;
    if (!aKeys.every((key, index) => key === bKeys[index])) return false;
    return aKeys.every((key) => jsonEqual(a[key] as JsonValue, b[key] as JsonValue));
  }
  return false;
}

function preview(value: JsonValue): string {
  const text = JSON.stringify(value) ?? 'undefined';
  return text.length > 120 ? `${text.slice(0, 117)}…` : text;
}

// eslint-disable-next-line complexity -- one function per keyword would scatter a closed, ~30-branch dispatch over thirty files without making any branch clearer.
function validateNode(registry: SchemaRegistry, schema: JsonValue, instance: JsonValue, ctx: Context): void {
  if (schema === true) return;
  if (schema === false) {
    fail(ctx, 'false', 'this position admits no value at all.');
    return;
  }
  if (!isPlainObject(schema)) {
    fail(ctx, 'schema', 'schema is neither an object nor a boolean.');
    return;
  }

  const ref = schema['$ref'];
  if (typeof ref === 'string') {
    const resolved = registry.resolve(ref, ctx.baseId);
    const targetBase = resolved.path.slice(0, resolved.path.indexOf('#'));
    validateNode(registry, resolved.schema, instance, {
      baseId: targetBase,
      instancePath: ctx.instancePath,
      schemaPath: resolved.path,
      errors: ctx.errors,
    });
    // 2020-12: $ref siblings still apply. Fall through.
  }

  const kind = typeOf(instance);

  const typeKeyword = schema['type'];
  if (typeKeyword !== undefined) {
    const names = (Array.isArray(typeKeyword) ? typeKeyword : [typeKeyword]) as readonly string[];
    if (!names.some((name) => matchesType(instance, name))) {
      fail(ctx, 'type', `expected ${names.join(' or ')}, got ${kind} (${preview(instance)}).`);
    }
  }

  const constKeyword = schema['const'];
  if (constKeyword !== undefined && !jsonEqual(instance, constKeyword)) {
    fail(ctx, 'const', `must equal ${preview(constKeyword)}, got ${preview(instance)}.`);
  }

  const enumKeyword = schema['enum'];
  if (Array.isArray(enumKeyword) && !enumKeyword.some((candidate) => jsonEqual(instance, candidate))) {
    fail(ctx, 'enum', `${preview(instance)} is not one of ${preview(enumKeyword as JsonValue)}.`);
  }

  if (typeof instance === 'string') {
    validateString(schema, instance, ctx);
  }
  if (typeof instance === 'number') {
    validateNumber(schema, instance, ctx);
  }
  if (Array.isArray(instance)) {
    validateArray(registry, schema, instance, ctx);
  }
  if (isPlainObject(instance)) {
    validateObject(registry, schema, instance, ctx);
  }

  validateApplicators(registry, schema, instance, ctx);
}

function validateString(schema: Record<string, JsonValue>, instance: string, ctx: Context): void {
  // Length is measured in Unicode code points, as the specification requires — not in
  // UTF-16 units, which would make an emoji count twice and a limit mean two things.
  const length = [...instance].length;
  const minLength = schema['minLength'];
  if (typeof minLength === 'number' && length < minLength) {
    fail(ctx, 'minLength', `needs at least ${minLength} characters, has ${length}.`);
  }
  const maxLength = schema['maxLength'];
  if (typeof maxLength === 'number' && length > maxLength) {
    fail(ctx, 'maxLength', `allows at most ${maxLength} characters, has ${length}.`);
  }
  const pattern = schema['pattern'];
  if (typeof pattern === 'string' && !new RegExp(pattern, 'u').test(instance)) {
    fail(ctx, 'pattern', `${preview(instance)} does not match /${pattern}/.`);
  }
  const format = schema['format'];
  if (typeof format === 'string') {
    const check = FORMATS[format];
    if (check !== undefined && !check(instance)) {
      fail(ctx, 'format', `${preview(instance)} is not a valid ${format}.`);
    }
  }
}

function validateNumber(schema: Record<string, JsonValue>, instance: number, ctx: Context): void {
  const minimum = schema['minimum'];
  if (typeof minimum === 'number' && instance < minimum) {
    fail(ctx, 'minimum', `must be >= ${minimum}, got ${instance}.`);
  }
  const maximum = schema['maximum'];
  if (typeof maximum === 'number' && instance > maximum) {
    fail(ctx, 'maximum', `must be <= ${maximum}, got ${instance}.`);
  }
  const exclusiveMinimum = schema['exclusiveMinimum'];
  if (typeof exclusiveMinimum === 'number' && instance <= exclusiveMinimum) {
    fail(ctx, 'exclusiveMinimum', `must be > ${exclusiveMinimum}, got ${instance}.`);
  }
  const exclusiveMaximum = schema['exclusiveMaximum'];
  if (typeof exclusiveMaximum === 'number' && instance >= exclusiveMaximum) {
    fail(ctx, 'exclusiveMaximum', `must be < ${exclusiveMaximum}, got ${instance}.`);
  }
  const multipleOf = schema['multipleOf'];
  if (typeof multipleOf === 'number' && multipleOf > 0) {
    const quotient = instance / multipleOf;
    if (Math.abs(quotient - Math.round(quotient)) > 1e-9) {
      fail(ctx, 'multipleOf', `must be a multiple of ${multipleOf}, got ${instance}.`);
    }
  }
}

function validateArray(
  registry: SchemaRegistry,
  schema: Record<string, JsonValue>,
  instance: readonly JsonValue[],
  ctx: Context,
): void {
  const minItems = schema['minItems'];
  if (typeof minItems === 'number' && instance.length < minItems) {
    fail(ctx, 'minItems', `needs at least ${minItems} items, has ${instance.length}.`);
  }
  const maxItems = schema['maxItems'];
  if (typeof maxItems === 'number' && instance.length > maxItems) {
    fail(ctx, 'maxItems', `allows at most ${maxItems} items, has ${instance.length}.`);
  }
  if (schema['uniqueItems'] === true) {
    for (let i = 0; i < instance.length; i += 1) {
      for (let j = i + 1; j < instance.length; j += 1) {
        if (jsonEqual(instance[i] as JsonValue, instance[j] as JsonValue)) {
          fail(ctx, 'uniqueItems', `items ${i} and ${j} are equal.`);
        }
      }
    }
  }

  const prefixItems = schema['prefixItems'];
  let prefixCount = 0;
  if (Array.isArray(prefixItems)) {
    prefixCount = Math.min(prefixItems.length, instance.length);
    for (let i = 0; i < prefixCount; i += 1) {
      validateNode(
        registry,
        prefixItems[i] as JsonValue,
        instance[i] as JsonValue,
        child(ctx, String(i), `/prefixItems/${i}`),
      );
    }
  }

  const items = schema['items'];
  if (items !== undefined) {
    for (let i = prefixCount; i < instance.length; i += 1) {
      validateNode(registry, items, instance[i] as JsonValue, child(ctx, String(i), '/items'));
    }
  }

  const contains = schema['contains'];
  if (contains !== undefined) {
    let matched = 0;
    for (const item of instance) {
      const probe = branch(ctx, '/contains');
      validateNode(registry, contains, item, probe.ctx);
      if (probe.errors.length === 0) matched += 1;
    }
    const minContains = typeof schema['minContains'] === 'number' ? schema['minContains'] : 1;
    const maxContains = typeof schema['maxContains'] === 'number' ? schema['maxContains'] : Infinity;
    if (matched < minContains) {
      fail(ctx, 'contains', `needs at least ${minContains} matching item(s), found ${matched}.`);
    }
    if (matched > maxContains) {
      fail(ctx, 'maxContains', `allows at most ${maxContains} matching item(s), found ${matched}.`);
    }
  }
}

function validateObject(
  registry: SchemaRegistry,
  schema: Record<string, JsonValue>,
  instance: Record<string, JsonValue>,
  ctx: Context,
): void {
  const keys = Object.keys(instance);

  const required = schema['required'];
  if (Array.isArray(required)) {
    for (const name of required as readonly string[]) {
      if (!Object.hasOwn(instance, name)) {
        fail(ctx, 'required', `property "${name}" is required and is absent.`);
      }
    }
  }

  const minProperties = schema['minProperties'];
  if (typeof minProperties === 'number' && keys.length < minProperties) {
    fail(ctx, 'minProperties', `needs at least ${minProperties} properties, has ${keys.length}.`);
  }
  const maxProperties = schema['maxProperties'];
  if (typeof maxProperties === 'number' && keys.length > maxProperties) {
    fail(ctx, 'maxProperties', `allows at most ${maxProperties} properties, has ${keys.length}.`);
  }

  const dependentRequired = schema['dependentRequired'];
  if (isPlainObject(dependentRequired)) {
    for (const [trigger, names] of Object.entries(dependentRequired)) {
      if (!Object.hasOwn(instance, trigger) || !Array.isArray(names)) continue;
      for (const name of names as readonly string[]) {
        if (!Object.hasOwn(instance, name)) {
          fail(ctx, 'dependentRequired', `"${trigger}" is present, so "${name}" is required and is absent.`);
        }
      }
    }
  }

  const dependentSchemas = schema['dependentSchemas'];
  if (isPlainObject(dependentSchemas)) {
    for (const [trigger, sub] of Object.entries(dependentSchemas)) {
      if (!Object.hasOwn(instance, trigger)) continue;
      validateNode(registry, sub, instance, child(ctx, null, `/dependentSchemas/${pointerSegment(trigger)}`));
    }
  }

  const propertyNames = schema['propertyNames'];
  if (propertyNames !== undefined) {
    for (const key of keys) {
      validateNode(registry, propertyNames, key, child(ctx, key, '/propertyNames'));
    }
  }

  const properties = isPlainObject(schema['properties']) ? schema['properties'] : undefined;
  const patternProperties = isPlainObject(schema['patternProperties'])
    ? schema['patternProperties']
    : undefined;

  if (properties !== undefined) {
    for (const [name, sub] of Object.entries(properties)) {
      if (!Object.hasOwn(instance, name)) continue;
      validateNode(
        registry,
        sub,
        instance[name] as JsonValue,
        child(ctx, name, `/properties/${pointerSegment(name)}`),
      );
    }
  }

  if (patternProperties !== undefined) {
    for (const [pattern, sub] of Object.entries(patternProperties)) {
      const regex = new RegExp(pattern, 'u');
      for (const key of keys) {
        if (!regex.test(key)) continue;
        validateNode(
          registry,
          sub,
          instance[key] as JsonValue,
          child(ctx, key, `/patternProperties/${pointerSegment(pattern)}`),
        );
      }
    }
  }

  const additionalProperties = schema['additionalProperties'];
  if (additionalProperties !== undefined) {
    for (const key of keys) {
      if (properties !== undefined && Object.hasOwn(properties, key)) continue;
      if (
        patternProperties !== undefined &&
        Object.keys(patternProperties).some((pattern) => new RegExp(pattern, 'u').test(key))
      ) {
        continue;
      }
      if (additionalProperties === false) {
        // The error points at the OFFENDING PROPERTY, not at its parent. A message that
        // says "this object has an undeclared field" without naming it makes a
        // twenty-field payload a search problem.
        fail(
          child(ctx, key, ''),
          'additionalProperties',
          `property "${key}" is not declared by this contract. An undeclared field in an evidentiary ` +
            'payload is a field nobody agreed to render, so it is refused rather than ignored.',
        );
        continue;
      }
      validateNode(
        registry,
        additionalProperties,
        instance[key] as JsonValue,
        child(ctx, key, '/additionalProperties'),
      );
    }
  }
}

function validateApplicators(
  registry: SchemaRegistry,
  schema: Record<string, JsonValue>,
  instance: JsonValue,
  ctx: Context,
): void {
  const allOf = schema['allOf'];
  if (Array.isArray(allOf)) {
    allOf.forEach((sub, index) => {
      validateNode(registry, sub, instance, child(ctx, null, `/allOf/${index}`));
    });
  }

  const anyOf = schema['anyOf'];
  if (Array.isArray(anyOf)) {
    const collected: ValidationError[][] = [];
    const ok = anyOf.some((sub, index) => {
      const probe = branch(ctx, `/anyOf/${index}`);
      validateNode(registry, sub, instance, probe.ctx);
      if (probe.errors.length > 0) collected.push(probe.errors);
      return probe.errors.length === 0;
    });
    if (!ok) {
      fail(
        ctx,
        'anyOf',
        `no alternative matched. Closest failures: ${collected
          .map((errs) => errs[0]?.message ?? 'unknown')
          .slice(0, 3)
          .join(' | ')}`,
      );
    }
  }

  const oneOf = schema['oneOf'];
  if (Array.isArray(oneOf)) {
    const matched: number[] = [];
    const collected: ValidationError[][] = [];
    oneOf.forEach((sub, index) => {
      const probe = branch(ctx, `/oneOf/${index}`);
      validateNode(registry, sub, instance, probe.ctx);
      if (probe.errors.length === 0) matched.push(index);
      else collected.push(probe.errors);
    });
    if (matched.length === 0) {
      fail(
        ctx,
        'oneOf',
        `no alternative matched. Closest failures: ${collected
          .map((errs) => errs[0]?.message ?? 'unknown')
          .slice(0, 3)
          .join(' | ')}`,
      );
    } else if (matched.length > 1) {
      fail(ctx, 'oneOf', `${matched.length} alternatives matched (${matched.join(', ')}); exactly one must.`);
    }
  }

  const not = schema['not'];
  if (not !== undefined) {
    const probe = branch(ctx, '/not');
    validateNode(registry, not, instance, probe.ctx);
    if (probe.errors.length === 0) {
      fail(ctx, 'not', 'value matched a schema it must not match.');
    }
  }

  const ifSchema = schema['if'];
  if (ifSchema !== undefined) {
    const probe = branch(ctx, '/if');
    validateNode(registry, ifSchema, instance, probe.ctx);
    const conditionHeld = probe.errors.length === 0;
    const consequent = conditionHeld ? schema['then'] : schema['else'];
    if (consequent !== undefined) {
      validateNode(registry, consequent, instance, child(ctx, null, conditionHeld ? '/then' : '/else'));
    }
  }
}

/** Formats a result for a test failure message or a console error state. */
export function formatErrors(errors: readonly ValidationError[], limit = 12): string {
  if (errors.length === 0) return 'no errors';
  const shown = errors.slice(0, limit).map((error) => `  ${error.instancePath}  ${error.keyword}: ${error.message}\n    (${error.schemaPath})`);
  const rest = errors.length > limit ? `\n  … and ${errors.length - limit} more` : '';
  return `${errors.length} validation error(s):\n${shown.join('\n')}${rest}`;
}
