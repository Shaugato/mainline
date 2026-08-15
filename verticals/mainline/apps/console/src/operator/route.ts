// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE OPERATOR ROUTER — hash-based, two modules, no library.
 *
 * Hash routing for the same reason the console uses it: the built page must load from a bare
 * static host, from a sub-path and from `file://`, and `static_site.py` serves
 * `dist/operator.html` at `/operator.html` with no route table of its own
 * (operator-systems-plan.md M5). A path router would need a server that knows about it.
 *
 * ── THE SCREEN REGISTRY, AND WHY IT IS INVERTED ──────────────────────────────────────
 *
 * The two screens are built by other workers (`src/operator/permit/**` and
 * `src/operator/change/**`) and do not exist while this file is being written. So the shell
 * does not import them: each screen module SELF-REGISTERS by calling `registerScreen()` at
 * import time, and `boot.ts` discovers the modules with an enumerated `import.meta.glob`,
 * which expands to nothing when they are absent and to static imports when they land.
 *
 * The contract for the two screen owners is one line each:
 *
 *   • `src/operator/permit/screen.ts` calls `registerScreen('permit', mount)` at module scope.
 *   • `src/operator/change/screen.ts` calls `registerScreen('change', mount)` at module scope.
 *
 * A route with no registered screen renders a sentence saying so. It never renders a
 * placeholder that could be mistaken for a screen with no data in it — an empty permit form
 * and an unbuilt permit form must not look the same.
 */

/** The two modules this deployment carries. Order is the order they appear in the bar. */
export const OPERATOR_ROUTES = ['permit', 'change'] as const;

export type OperatorRoute = (typeof OPERATOR_ROUTES)[number];

/** Where an unrecognised, empty or absent hash lands. */
export const DEFAULT_ROUTE: OperatorRoute = 'permit';

export interface ModuleDescriptor {
  readonly route: OperatorRoute;
  /** The literal hash, including the `#`. */
  readonly hash: string;
  /** The module's name as the app bar prints it. */
  readonly name: string;
  /**
   * The left-rail register this module sits under, or `null` when it sits under none of
   * them. Management of change is not one of the four registers a control-of-work rail
   * lists, and inventing a home for it would be a small lie about how these systems are
   * organised.
   */
  readonly railSection: string | null;
}

export const MODULES: readonly ModuleDescriptor[] = [
  { route: 'permit', hash: '#/permit', name: 'Permit to work', railSection: 'Permits' },
  { route: 'change', hash: '#/change', name: 'Management of change', railSection: null },
];

export function isOperatorRoute(value: unknown): value is OperatorRoute {
  return (OPERATOR_ROUTES as readonly unknown[]).includes(value);
}

export function moduleFor(route: OperatorRoute): ModuleDescriptor {
  const found = MODULES.find((entry) => entry.route === route);
  if (found === undefined) {
    // Unreachable while MODULES covers OPERATOR_ROUTES, which route.test.ts asserts.
    // Throwing beats a default: a missing descriptor would print an empty module name in
    // the bar and look like a styling defect rather than a missing route.
    throw new Error(`operator/route: no module descriptor for route "${route}".`);
  }
  return found;
}

export function hashFor(route: OperatorRoute): string {
  return moduleFor(route).hash;
}

/**
 * Reads a route out of a location hash.
 *
 * Total and non-throwing: an unknown, malformed, empty or absent hash resolves to
 * {@link DEFAULT_ROUTE}. A router that throws on a hand-typed URL is a router that shows a
 * blank page to somebody who mistyped one character.
 */
export function routeFromHash(hash: string): OperatorRoute {
  const withoutHash = hash.startsWith('#') ? hash.slice(1) : hash;
  // Drop a query or a nested fragment: `#/permit?raw=1` is still the permit module.
  const path = withoutHash.split(/[?&]/)[0] ?? '';
  const segment = path.split('/').find((part) => part !== '') ?? '';
  return isOperatorRoute(segment) ? segment : DEFAULT_ROUTE;
}

/** The route the given window is currently showing. */
export function currentRoute(win: Pick<Window, 'location'> = window): OperatorRoute {
  return routeFromHash(win.location.hash);
}

/**
 * Mounts a screen into `host`.
 *
 * Returns a teardown function when the screen has anything to tear down (a listener, an
 * `AbortController` over an in-flight request), and `undefined` when it has nothing to undo.
 *
 * `undefined` and not `void`: `@typescript-eslint/no-invalid-void-type` refuses `void` inside
 * a union, and it is right to — `void` means "ignore whatever this returns", which is not what
 * is meant here. The cost is one explicit `return undefined;` in a screen that only writes
 * DOM, and the compiler names that requirement precisely rather than accepting a value the
 * shell would then try to call.
 */
export type ScreenMount = (host: HTMLElement) => (() => void) | undefined;

const screens = new Map<OperatorRoute, ScreenMount>();

/**
 * Declares which screen serves a route.
 *
 * Refuses a second registration for the same route rather than silently replacing it: two
 * modules claiming one route is a build mistake, and the version that wins would otherwise
 * depend on the order the glob happened to expand in.
 */
export function registerScreen(route: OperatorRoute, mount: ScreenMount): void {
  if (screens.has(route)) {
    throw new Error(
      `operator/route: a screen is already registered for "${route}". Two modules claiming one ` +
        'route means the one that renders depends on module evaluation order, which is not a ' +
        'thing anybody chose.',
    );
  }
  screens.set(route, mount);
}

export function screenFor(route: OperatorRoute): ScreenMount | null {
  return screens.get(route) ?? null;
}

export function registeredRoutes(): readonly OperatorRoute[] {
  return OPERATOR_ROUTES.filter((route) => screens.has(route));
}

/** Empties the registry. For tests, and for a shell that is being re-booted in place. */
export function clearScreens(): void {
  screens.clear();
}

/**
 * Calls `listener` whenever the hash changes, and hands back the unsubscribe.
 *
 * It does NOT fire on subscribe. The caller has already rendered the current route by the
 * time it subscribes, and firing immediately would render it twice.
 */
export function onRouteChange(
  listener: (route: OperatorRoute) => void,
  win: Window = window,
): () => void {
  const handler = (): void => {
    listener(routeFromHash(win.location.hash));
  };
  win.addEventListener('hashchange', handler);
  return () => {
    win.removeEventListener('hashchange', handler);
  };
}
