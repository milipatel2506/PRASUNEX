"""Synthetic school data generator.

Creates realistic weekly records (attendance, homework, subject marks, behaviour
incidents) for a population of students. A fraction of students are "strugglers"
whose signals start to slide at some onset week, in one of several patterns
(attendance-led, academic-led, homework-led, behaviour-led, or mixed).

NOTE: this is synthetic data for the prototype. Real-school validation is a pilot step.
"""
import numpy as np
import pandas as pd

SUBJECTS = ["maths", "science", "english", "social", "language"]
SUBJECT_LABEL = {"maths": "Maths", "science": "Science", "english": "English",
                 "social": "Social Science", "language": "Language"}

# weights per struggler type: (attendance, academics, homework, behaviour)
TYPE_WEIGHTS = np.array([
    [1.0, 0.3, 0.3, 0.1],   # 0 attendance-led
    [0.1, 1.0, 0.5, 0.1],   # 1 academic-led
    [0.1, 0.5, 1.0, 0.1],   # 2 homework-led
    [0.2, 0.4, 0.3, 1.0],   # 3 behaviour-led
    [0.7, 0.7, 0.7, 0.5],   # 4 mixed
])

FEATURES = [
    "att_first4", "att_last4", "att_drop",
    "marks_first4", "marks_last4", "marks_drop", "marks_vol",
    "min_subj_last4", "n_below_pass",
    "hw_first4", "hw_last4", "hw_drop",
    "inc_first4", "inc_last4",
]


def generate(n: int, seed: int, weeks: int = 12) -> dict:
    rng = np.random.default_rng(seed)
    ability = np.clip(rng.normal(68, 11, n), 40, 96)
    subj_off = rng.normal(0, 5, (n, 5))
    struggler = rng.random(n) < 0.26
    onset = rng.integers(2, 7, n)
    stype = rng.integers(0, 5, n)
    sev = rng.uniform(0.8, 1.5, n)
    focus = rng.integers(0, 5, n)
    gender = rng.choice(["F", "M"], n)

    t = np.arange(1, weeks + 1)[None, :]
    since = np.clip(t - onset[:, None], 0, None) * struggler[:, None]
    w = TYPE_WEIGHTS[stype] * struggler[:, None]

    base_att = np.clip(rng.normal(0.93, 0.04, n), 0.7, 1.0)
    att = base_att[:, None] - 0.028 * sev[:, None] * w[:, [0]] * since + rng.normal(0, 0.02, (n, weeks))
    att = np.clip(att, 0.3, 1.0)

    base_hw = np.clip(rng.normal(0.86, 0.10, n), 0.4, 1.0)
    hw = base_hw[:, None] - 0.05 * sev[:, None] * w[:, [2]] * since + rng.normal(0, 0.05, (n, weeks))
    hw = np.clip(hw, 0.0, 1.0)

    subj_weight = np.full((n, 5), 0.7)
    subj_weight[np.arange(n), focus] = 1.6
    drop = 2.6 * sev[:, None, None] * w[:, [1]][:, :, None] * since[:, :, None] * subj_weight[:, None, :]
    marks = ability[:, None, None] + subj_off[:, None, :] - drop + rng.normal(0, 6, (n, weeks, 5))
    marks = np.clip(marks, 0, 100)

    lam = 0.04 + 0.30 * sev[:, None] * w[:, [3]] * (since > 0)
    inc = rng.poisson(lam)

    return dict(att=att, hw=hw, marks=marks, inc=inc, ability=ability,
                struggler=struggler, stype=stype, gender=gender)


def features(d: dict, upto: int = 8) -> tuple[pd.DataFrame, np.ndarray]:
    """Features from weeks 1..upto (default 8). Returns (frame, weakest-subject index)."""
    h = upto // 2
    att = d["att"][:, :upto]
    hw = d["hw"][:, :upto]
    marks = d["marks"][:, :upto, :]
    inc = d["inc"][:, :upto]
    wk = marks.mean(2)
    subj_last = marks[:, h:upto, :].mean(1)
    f = pd.DataFrame({
        "att_first4": att[:, :h].mean(1),
        "att_last4": att[:, h:].mean(1),
        "marks_first4": wk[:, :h].mean(1),
        "marks_last4": wk[:, h:].mean(1),
        "marks_vol": np.diff(wk, axis=1).std(1),
        "min_subj_last4": subj_last.min(1),
        "n_below_pass": (subj_last < 40).sum(1),
        "hw_first4": hw[:, :h].mean(1),
        "hw_last4": hw[:, h:].mean(1),
        "inc_first4": inc[:, :h].sum(1),
        "inc_last4": inc[:, h:].sum(1),
    })
    f["att_drop"] = f.att_first4 - f.att_last4
    f["marks_drop"] = f.marks_first4 - f.marks_last4
    f["hw_drop"] = f.hw_first4 - f.hw_last4
    return f[FEATURES], subj_last.argmin(1)


def label(d: dict, upto: int = 8) -> np.ndarray:
    """At risk = weeks after `upto` end with a failing average, or a sharp fall."""
    past = d["marks"][:, :upto, :].mean((1, 2))
    future = d["marks"][:, upto:, :].mean((1, 2))
    return ((future < 50) | (future < past - 8)).astype(int)
