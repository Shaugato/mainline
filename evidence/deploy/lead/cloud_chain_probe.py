"""Apply the MAINLINE migration chain to CockroachDB Cloud, with 40001 retry.

Measures: does the chain apply to a multi-node Cloud Basic cluster, how long does
it take, and which files need a retry that the local single node never provokes.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg

REPO = Path("D:/CoackroachDBxAWS/mainline")
MIGRATIONS = REPO / "verticals" / "mainline" / "db" / "migrations"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("cloud_chain.json")
DB = sys.argv[1] if len(sys.argv) > 1 else "w_deploy_cloud_probe"


def rewrite(dsn: str, database: str) -> str:
    parts = urlsplit(dsn)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q["connect_timeout"] = "20"
    q["application_name"] = "mainline-deploy-probe"
    return urlunsplit((parts.scheme, parts.netloc, "/" + database, urlencode(q), parts.fragment))


def discover() -> list[Path]:
    pat = re.compile(r"^(\d{4})([a-z]?)_[a-z0-9_]+\.sql$")
    out = []
    for p in sorted(MIGRATIONS.glob("*.sql")):
        m = pat.match(p.name)
        if m:
            out.append((int(m.group(1)), m.group(2), p))
    out.sort(key=lambda t: (t[0], t[1]))
    return [p for _, _, p in out]


def main() -> int:
    admin = os.environ["COCKROACH_DSN"]
    started = time.time()
    with psycopg.connect(rewrite(admin, "defaultdb"), autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{DB}" CASCADE')
        c.execute(f'CREATE DATABASE "{DB}"')
        zone = None
        try:
            c.execute(f'ALTER DATABASE "{DB}" CONFIGURE ZONE USING gc.ttlseconds = 4500')
            zone = 4500
        except psycopg.Error as e:
            zone = f"REFUSED: {e}"
    print(f"database ready in {time.time() - started:.1f}s; zone={zone}", flush=True)

    dsn = rewrite(admin, DB)
    # bootstrap the trappoint bookkeeping schema via the CLI, same as the proof does
    import subprocess

    t0 = time.time()
    boot = subprocess.run(
        [str(REPO / ".venv/Scripts/trappoint.exe"), "migrate", "bootstrap", "--dsn", dsn],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    print(f"bootstrap rc={boot.returncode} in {time.time() - t0:.1f}s", flush=True)
    if boot.returncode != 0:
        print(boot.stdout[-2000:], boot.stderr[-2000:], flush=True)

    paths = discover()
    rows = []
    applied = failed = retried = 0
    conn = psycopg.connect(dsn, autocommit=True)
    for i, p in enumerate(paths, 1):
        sql = p.read_text(encoding="utf-8")
        attempts = 0
        t0 = time.time()
        err = None
        state = None
        while attempts < 6:
            attempts += 1
            try:
                conn.execute(sql)  # type: ignore[arg-type]
                err = None
                break
            except psycopg.Error as e:
                state = getattr(e, "sqlstate", None) or (
                    e.diag.sqlstate if getattr(e, "diag", None) else None
                )
                err = str(e).splitlines()[0][:300]
                if state == "40001":
                    time.sleep(0.25 * attempts)
                    continue
                break
            except Exception as e:  # connection died
                err = f"{type(e).__name__}: {e}"[:300]
                try:
                    conn.close()
                except Exception:
                    pass
                conn = psycopg.connect(dsn, autocommit=True)
                time.sleep(0.5 * attempts)
                continue
        secs = time.time() - t0
        if err is None:
            applied += 1
            if attempts > 1:
                retried += 1
        else:
            failed += 1
        rows.append(
            {
                "file": p.name,
                "seconds": round(secs, 3),
                "attempts": attempts,
                "sqlstate": state if err else "00000",
                "error": err,
            }
        )
        if i % 20 == 0 or err:
            print(
                f"[{i}/{len(paths)}] {p.name} {'OK' if err is None else 'FAIL ' + str(state)} "
                f"{secs:.2f}s a={attempts}",
                flush=True,
            )
    total = time.time() - started
    doc = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "target": "CockroachDB Cloud Basic, aws-ap-southeast-1, mainline-dev",
        "database": DB,
        "zone_gc_ttlseconds": zone,
        "files": len(paths),
        "applied": applied,
        "failed": failed,
        "files_that_needed_a_retry": retried,
        "total_seconds": round(total, 1),
        "slowest": sorted(rows, key=lambda r: -r["seconds"])[:15],
        "failures": [r for r in rows if r["error"]],
        "rows": rows,
    }
    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(
        f"DONE files={len(paths)} applied={applied} failed={failed} retried={retried} "
        f"total={total:.1f}s -> {OUT}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
