"""Re-score one student from their stored weekly records (used after weekly data entry)."""
from __future__ import annotations
import json
import sqlite3

import numpy as np

from . import datagen, model

MIN_WEEKS = 4   # fewer weeks than this is not enough history to score
WINDOW = 8      # the model was trained on 8-week windows


def rescore(con: sqlite3.Connection, sid: int) -> bool:
    """Compute and store the risk for a student. Returns False if there is not enough history yet.

    Built-in subjects always count. A subject the faculty added counts from the first week it has marks (the latest
    week must have them). Weeks before that are filled with the student's own average for that week, which leaves the
    earlier trend unchanged instead of inventing a drop or a rise."""
    rows = con.execute("SELECT * FROM weekly WHERE student_id=? ORDER BY week DESC LIMIT ?", (sid, WINDOW)).fetchall()[::-1]
    if len(rows) < MIN_WEEKS:
        return False
    weeks = [r["week"] for r in rows]
    extra: dict[str, dict[int, float]] = {}
    for e in con.execute("SELECT subject, week, marks FROM weekly_extra WHERE student_id=? AND week BETWEEN ? AND ?",
                         (sid, weeks[0], weeks[-1])):
        extra.setdefault(e["subject"], {})[e["week"]] = e["marks"]
    names = sorted(n for n, m in extra.items() if weeks[-1] in m)
    labels = list(datagen.SUBJECTS) + ["x:" + n for n in names]
    d = {
        "att": np.array([[r["attendance"] for r in rows]]),
        "hw": np.array([[r["homework"] for r in rows]]),
        "inc": np.array([[r["incidents"] for r in rows]]),
        "marks": np.array([[[r[s] for s in datagen.SUBJECTS] + [extra[n].get(r["week"], float(np.mean([r[s] for s in datagen.SUBJECTS]))) for n in names]
                   for r in rows]]),
    }
    X, weak = datagen.features(d, upto=len(rows))
    sc = model.score(X)[0]
    con.execute("INSERT OR REPLACE INTO risk(student_id,risk,tier,reasons,weakest_subject,asof_week) VALUES(?,?,?,?,?,?)",
                (sid, sc["risk"], sc["tier"], json.dumps(sc["reasons"]), labels[int(weak[0])], rows[-1]["week"]))
    return True
