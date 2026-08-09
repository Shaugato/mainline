// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ONE DIMENSIONAL SURFACE.
 *
 * `src/features/ancestry/AncestryScreen.tsx` reaches this module through exactly one
 * lazy import, inside an error boundary that falls back to the ribbon. That is the
 * entire inbound edge of the MEMORY register, and it is why deleting this directory is
 * a supported operation rather than a breakage (`BUILD_PLAN` §10.2, cut 1).
 *
 * Read `docs/dimensionality-charter.md` before changing anything here. Every rule it
 * states is enforced by a test in `tests/unit/ancestry-3d/`, and the rules are the
 * reason this surface is defensible in a room where a judge is looking at a fatality
 * record.
 *
 * ── THE SHAPE OF THIS FILE ───────────────────────────────────────────────────────
 *
 *   1. Refuse to be here at all if motion is refused (belt to the capability probe's
 *      braces — the probe should already have chosen the ribbon).
 *   2. Project the layout ONCE. `projectWalk` throws on a person field, an incoherent
 *      time axis or an edge to nowhere; a throw here reaches the ancestry screen's
 *      error boundary and the reader gets the ribbon, which carries every fact.
 *   3. Build the animation registry from the projected scene, so the stillness rule is
 *      derived from the same severities the geometry was built from.
 *   4. Mount a canvas whose frame loop is either the browser's (live) or exactly N
 *      manual advances (cinema).
 *   5. Grade the first thirty frames and descend the quality ladder, or hand back.
 */

import { Canvas } from '@react-three/fiber';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
} from 'react';
import { useThree } from '@react-three/fiber';

import { useMotionAllowed } from '../../../design/motion';
import { buildSceneRegistry } from './animation-registry';
import { readCinema } from './cinema';
import type { AncestryLayout } from './contract';
import { WalkControls } from './Controls';
import { buildLabels } from './label-model';
import { LabelLayer } from './Labels';
import { computedStyleReader, resolvePalette } from './palette';
import { SCENE_DEPTH, projectWalk, sceneGraphOf } from './projection';
import {
  RAIL_EYE_HEIGHT,
  RAIL_FOV_DEGREES,
  railLengthFor,
  setControl as setRailsControl,
  type RailsControl,
} from './rails';
import {
  createFrameSampler,
  detailBudgetFor,
  gradeWindow,
  QUALITY_SAMPLE_FRAMES,
  type DetailTier,
} from './quality';
import { createWalkRuntime, type WalkRuntime } from './runtime';
import styles from './walk.module.css';
import { WalkSceneContents } from './WalkScene';

/**
 * Drives the canvas by hand under cinema mode.
 *
 * Inside the canvas on purpose: a child's effect runs after the whole tree is mounted,
 * so `advance` is guaranteed to render a complete scene. Reaching for the root state
 * from the parent's effect is a race that shows up as a blank first capture on a slow
 * runner, which is the exact failure a pixel baseline exists to catch and the exact
 * failure it would be blamed for.
 *
 * The camera position is `railsAtFrame(frame)` — a pure function of `?frame=` — so the
 * number of advances does not change the image. Advancing N times rather than once is
 * what makes the capture exercise the real per-frame path N times instead of asserting
 * over a path the live console never takes.
 */
function CinemaDriver({
  frame,
  runtime,
  onAdvanced,
}: {
  readonly frame: number;
  readonly runtime: WalkRuntime;
  readonly onAdvanced: (count: number) => void;
}): null {
  const advance = useThree((state) => state.advance);

  useEffect(() => {
    const count = Math.max(1, frame);
    for (let index = 0; index < count; index += 1) {
      // A synthetic, monotonically increasing timestamp at exactly 60 Hz. The scene does
      // not read it — `railsAtFrame` is a function of the index — but r3f's own clock
      // does, and feeding it wall time would make the internal delta a function of the
      // runner.
      advance((index * 1000) / 60, true);
    }
    // Reported from the frame loop's OWN counter rather than from the loop bound above.
    // That is the stronger claim: it says the per-frame path actually ran N times, not
    // merely that `advance()` was called N times into a tree that might not have been
    // subscribed yet.
    onAdvanced(runtime.framesAdvanced);
  }, [advance, frame, onAdvanced, runtime]);

  return null;
}

export interface WalkCanvasProps {
  /**
   * The layout the ribbon renders. Consumed unchanged: this surface adds a `z` from the
   * `t` that is already there and computes no graph of its own.
   */
  readonly layout: AncestryLayout;
  /**
   * Called when the quality ladder hands back. The host should render the ribbon.
   *
   * Optional: with no host handler the surface renders its own honest notice and a link
   * that reloads into the ribbon, so a hand-back never leaves a blank rectangle even if
   * the host forgot to handle it.
   */
  readonly onHandBack?: () => void;
  readonly className?: string;
}

export function WalkCanvas({ layout, onHandBack, className }: WalkCanvasProps): JSX.Element {
  const cinema = useMemo(() => readCinema(), []);
  const motionAllowed = useMotionAllowed('memory');

  const scene = useMemo(() => projectWalk(layout), [layout]);
  const manifest = useMemo(() => sceneGraphOf(scene), [scene]);
  const registry = useMemo(() => buildSceneRegistry(scene.nodes), [scene]);
  const railLength = useMemo(() => railLengthFor(scene.deepestZ), [scene]);

  // Resolved once, from the live cascade, at first render — before any object is built,
  // so the scene is never constructed in the wrong colours and then corrected.
  const [palette] = useState(() =>
    resolvePalette(
      typeof document === 'undefined' ? undefined : computedStyleReader(document.documentElement),
    ),
  );

  // Lazily constructed and then kept for the life of the surface: the rails position is
  // per-frame state, and routing it through React would re-render the tree sixty times a
  // second (see `runtime.ts` for why that matters).
  const runtimeRef = useRef<WalkRuntime | null>(null);
  runtimeRef.current ??= createWalkRuntime(railLength);
  const runtime = runtimeRef.current;

  // A new layout is a new rail. Keep the runtime's length in step and clamp the reader's
  // position into the new range rather than leaving them past the end of a shorter walk.
  useEffect(() => {
    runtime.rails = {
      travel: Math.min(runtime.rails.travel, railLength),
      control: runtime.rails.control,
      railLength,
    };
  }, [railLength, runtime]);

  const [control, setControl] = useState<RailsControl>('back');
  const [tier, setTier] = useState<DetailTier>('full');
  const [framesAdvanced, setFramesAdvanced] = useState(0);
  const samplerRef = useRef(createFrameSampler(QUALITY_SAMPLE_FRAMES));

  useEffect(() => {
    runtime.rails = setRailsControl(runtime.rails, control);
  }, [control, runtime]);

  const onSample = useCallback(
    (frameMs: number) => {
      if (cinema.enabled) return;
      const sampler = samplerRef.current;
      sampler.push(frameMs);
      if (!sampler.full()) return;
      setTier((previous) => {
        const grade = gradeWindow(sampler.samples(), previous, { cinema: false });
        if (grade.tier !== previous) sampler.reset();
        return grade.tier;
      });
    },
    [cinema.enabled],
  );

  const budget = detailBudgetFor(tier);
  const labels = useMemo(() => buildLabels(scene, budget.labelStride), [scene, budget.labelStride]);

  const handedBack = tier === 'handback';
  useEffect(() => {
    if (handedBack) onHandBack?.();
  }, [handedBack, onHandBack]);

  const onAdvanced = useCallback((count: number) => {
    setFramesAdvanced(count);
  }, []);

  // Every machine-readable fact about the scene, on the container, so the browser spec
  // can assert scene-graph parity against the ribbon without a GPU read-back.
  const containerProps = {
    'data-walk': '1',
    'data-walk-node-ids': manifest.nodeIds.join(' '),
    'data-walk-edge-keys': manifest.edgeKeys.join(' '),
    'data-walk-still-ids': manifest.stillNodeIds.join(' '),
    'data-walk-lights': String(manifest.lightCount),
    'data-walk-draw-calls': String(manifest.bulkDrawCalls),
    'data-walk-tier': tier,
    'data-walk-time-unit': scene.timeUnit,
    'data-walk-truncated': scene.truncated ? '1' : '0',
    'data-walk-cinema': cinema.enabled ? '1' : '0',
    'data-walk-cinema-source': cinema.source,
    'data-walk-frames-advanced': String(framesAdvanced),
  } as const;

  const spine = (
    <ul className={styles.srOnly} data-walk-spine="1">
      {scene.nodes.map((node) => (
        <li key={node.id} data-walk-node-id={node.id} data-walk-node-kind={node.kind}>
          {node.kind} · {node.still ? 'severity 5 — still' : `severity ${node.severity}`}
        </li>
      ))}
    </ul>
  );

  // ── The refusals, before anything is drawn ────────────────────────────────────

  if (!cinema.enabled && !motionAllowed) {
    return (
      <div className={`${styles.walk} ${className ?? ''}`} {...containerProps} data-walk-refused="motion">
        {spine}
        <div className={styles.notice}>
          <p className={styles.noticeTitle}>The walk is not drawn on this machine.</p>
          <p>
            Motion is refused here — reduced motion, save-data or a low-memory signal. The ribbon
            renders the same layout projected on two axes and carries every node and every edge
            this walk would have drawn.
          </p>
          <a className={styles.noticeLink} href="?render=2d">
            ?render=2d
          </a>
        </div>
      </div>
    );
  }

  if (handedBack || !budget.renderCanvas) {
    return (
      <div className={`${styles.walk} ${className ?? ''}`} {...containerProps} data-walk-refused="frame-budget">
        {spine}
        <div className={styles.notice}>
          <p className={styles.noticeTitle}>The walk was handed back.</p>
          <p>
            This machine could not hold the frame budget, and a fatality is not something to stutter
            through. The ribbon carries every node and every edge the walk would have drawn.
          </p>
          <a className={styles.noticeLink} href="?render=2d">
            ?render=2d
          </a>
        </div>
      </div>
    );
  }

  // ── The surface ───────────────────────────────────────────────────────────────

  return (
    <div className={`${styles.walk} ${className ?? ''}`} {...containerProps}>
      {spine}

      <Canvas
        className={styles.canvasHost}
        // `flat` = NoToneMapping. The token colour must reach the pixel unmodified: a
        // tone-mapped severity accent is a different colour from the one the contrast
        // gate measured, and this scene has exactly one thing to say with colour.
        flat
        // Fixed device pixel ratio. A canvas whose resolution follows the display makes
        // a screenshot a function of the monitor.
        dpr={1}
        frameloop={cinema.enabled ? 'never' : 'always'}
        gl={{
          antialias: true,
          alpha: false,
          // Only under capture, and only because a screenshot may read the buffer after
          // the frame has been composited. It costs a copy per frame and the live path
          // does not pay it.
          preserveDrawingBuffer: cinema.enabled,
          powerPreference: 'high-performance',
        }}
        camera={{
          fov: RAIL_FOV_DEGREES,
          near: 0.1,
          far: SCENE_DEPTH + 80,
          position: [0, RAIL_EYE_HEIGHT, 0],
        }}
      >
        <color attach="background" args={[palette.void]} />
        <WalkSceneContents
          scene={scene}
          palette={palette}
          registry={registry}
          runtime={runtime}
          labels={labels}
          laneRails={budget.showLaneRails}
          dashedInferredEdges={budget.dashedInferredEdges}
          interactive={!cinema.enabled}
          cinemaFrame={cinema.enabled ? cinema.frame : null}
          onSample={onSample}
        />
        {cinema.enabled && (
          <CinemaDriver frame={cinema.frame} runtime={runtime} onAdvanced={onAdvanced} />
        )}
      </Canvas>

      <LabelLayer labels={labels} runtime={runtime} />

      <WalkControls control={control} onControl={setControl} enabled={railLength > 0} />

      <div className={styles.legend} data-walk-legend="1">
        <span>
          <span className={styles.legendMono}>———</span> asserted link
        </span>
        {/*
          The dash carries "this link is inferred". When the quality ladder drops the
          dashed draw call the FACT does not leave the console — the legend says so in
          words instead. An inferred edge shown as though it were asserted, with nothing
          on screen saying which it is, is the rubber stamp this product refuses to build.
        */}
        {budget.dashedInferredEdges ? (
          <span data-walk-inferred="dashed">
            <span className={styles.legendMono}>– – –</span> inferred link — a claim about the past
          </span>
        ) : (
          <span data-walk-inferred="collapsed">
            inferred links are drawn solid at this detail tier — the ribbon renders them
            distinctly
          </span>
        )}
        {scene.truncated && (
          <span data-walk-truncation="truncated">
            ancestry truncated — the ribbon carries the cap and the spilled count
          </span>
        )}
        {!scene.ancestryComplete && (
          <span data-walk-truncation="incomplete">
            ancestry incomplete — this walk is not the whole closure
          </span>
        )}
      </div>
    </div>
  );
}

export default WalkCanvas;
