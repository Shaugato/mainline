"""Three beats, one transaction, savepoints, total rollback. Does CockroachDB allow it?"""

from __future__ import annotations

import hashlib
import json

import psycopg
from psycopg.types.json import Jsonb

DSN = "postgresql://root@127.0.0.1:26257/proof_gate_final?sslmode=disable&connect_timeout=5"


def jcs(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":")).encode()


def st(e):
    return getattr(e, "sqlstate", None) or (e.diag.sqlstate if getattr(e, "diag", None) else "?")


conn = psycopg.connect(DSN, autocommit=False)
cur = conn.cursor()
cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
cur.execute("SELECT permit_id, gate_epoch, merged_commit, open_blocking FROM mainline.permit LIMIT 1")
permit_id, epoch, merged_commit, open_blocking = cur.fetchone()
print("start:", permit_id, "epoch", epoch, "open_blocking", open_blocking)

payload = {"permit": str(permit_id), "merged_by": "probe", "proof": "demo"}
canon = jcs(payload)
leaf = hashlib.sha256(b"\x00" + canon).digest()
cur.execute("SELECT commit_id FROM mainline.commit_obj LIMIT 1")
commit = merged_commit or cur.fetchone()[0]


def beat(label: str, before_sql: str | None):
    cur.execute("SAVEPOINT b")
    try:
        if before_sql:
            cur.execute(before_sql)
        cur.execute(
            "CALL mainline.merge_permit(%s,%s,%s,%s,%s,%s,%s,%s)",
            (permit_id, commit, "probe", "human", Jsonb(payload), canon, 1, leaf),
        )
        print(f"{label:14} ADMITTED  [00000]")
        cur.execute("ROLLBACK TO SAVEPOINT b")
    except psycopg.Error as e:
        print(f"{label:14} REFUSED   [{st(e)}] {str(e).splitlines()[0][:110]}")
        cur.execute("ROLLBACK TO SAVEPOINT b")
    # is the transaction still usable?
    cur.execute("SELECT 1")
    assert cur.fetchone() == (1,), "transaction died"


beat("open>0", "UPDATE mainline.permit SET open_blocking = 1 WHERE permit_id = '%s'" % permit_id)
beat("forged-zero", "UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = '%s'" % permit_id)
beat("as-is", None)

conn.rollback()
cur2 = psycopg.connect(DSN, autocommit=True).cursor()
cur2.execute("SELECT open_blocking FROM mainline.permit WHERE permit_id=%s", (permit_id,))
print("after rollback, open_blocking =", cur2.fetchone()[0], "(unchanged proves nothing persisted)")
