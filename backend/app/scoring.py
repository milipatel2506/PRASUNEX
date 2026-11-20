"""Re-score one student from their stored weekly records (used after weekly data entry)."""
from __future__ import annotations
import json
import sqlite3

import numpy as np

from . import datagen, model

MIN_WEEKS = 4   # fewer weeks than this is not enough history to score
WINDOW = 8      # the model was trained on 8-week windows


def rescore(con: sqlite3.Connection, sid: int) -> bool:
    """Compute and store the risk for a student. Returns False if there is not enough history yet."""
    rows = con.execute("SELECT * FROM weekly WHERE student_id=? ORDER BY week DESC LIMIT ?", (sid, WINDOW)).fetchall()[::-1]
    if len(rows) < MIN_WEEKS:
        return False
    d = {
        "att": np.array([[r["attendance"] for r in rows]]),
        "hw": np.array([[r["homework"] for r in rows]]),
        "inc": np.array([[r["incidents"] for r in rows]]),
        "marks": np.array([[[r[s] for s in datagen.SUBJECTS] for r in rows]]),
    }
    X, weak = datagen.features(d, upto=len(rows))
    sc = model.score(X)[0]
    con.execute("INSERT OR REPLACE INTO risk(student_id,risk,tier,reasons,weakest_subject,asof_week) VALUES(?,?,?,?,?,?)",
                (sid, sc["risk"], sc["tier"], json.dumps(sc["reasons"]), datagen.SUBJECTS[int(weak[0])], rows[-1]["week"]))
    return True
