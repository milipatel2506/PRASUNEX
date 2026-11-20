"""Risk engine: gradient boosting + SHAP explanations grouped into plain-language reasons."""
from __future__ import annotations
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

from . import datagen

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "risk_model.joblib"

HIGH, MEDIUM = 0.55, 0.25

# model feature -> reason category
CATEGORY = {
    "att_first4": "attendance", "att_last4": "attendance", "att_drop": "attendance",
    "marks_first4": "low_marks", "marks_drop": "marks_falling",
    "marks_last4": "low_marks", "min_subj_last4": "low_marks", "n_below_pass": "low_marks",
    "marks_vol": "volatile",
    "hw_first4": "homework", "hw_last4": "homework", "hw_drop": "homework",
    "inc_first4": "incidents", "inc_last4": "incidents",
}
CATEGORY_LABEL = {
    "attendance": "Attendance", "marks_falling": "Falling marks", "low_marks": "Low marks",
    "volatile": "Unstable scores", "homework": "Homework", "incidents": "Behaviour",
}


def tier_for(p: float) -> str:
    return "high" if p >= HIGH else "medium" if p >= MEDIUM else "low"


def _topk_metrics(y, score, frac=0.2):
    k = max(1, int(len(y) * frac))
    idx = np.argsort(-score)[:k]
    tp = y[idx].sum()
    return float(tp / k), float(tp / max(1, y.sum()))


def train(n: int = 6000, seed: int = 7) -> dict:
    d = datagen.generate(n, seed)
    X, _ = datagen.features(d)
    y = datagen.label(d)
    cut = int(n * 0.8)
    Xtr, Xte, ytr, yte = X.iloc[:cut], X.iloc[cut:], y[:cut], y[cut:]
    gte = d["gender"][cut:]

    gb = GradientBoostingClassifier(n_estimators=220, max_depth=3, learning_rate=0.08,
                                    subsample=0.8, random_state=seed)
    gb.fit(Xtr, ytr)
    p = gb.predict_proba(Xte)[:, 1]

    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
    lr.fit(Xtr, ytr)
    p_lr = lr.predict_proba(Xte)[:, 1]

    prec, rec = _topk_metrics(yte, p)
    # simple rule-of-thumb baseline: what a school might do by hand
    rule = ((Xte.att_last4 < 0.85) | (Xte.marks_last4 < 50) | (Xte.hw_last4 < 0.6)).to_numpy()
    rule_prec = float(yte[rule].mean()) if rule.any() else 0.0
    rule_rec = float(yte[rule].sum() / max(1, yte.sum()))

    top = p >= np.quantile(p, 0.8)
    fairness = {g: {"flag_rate": float(top[gte == g].mean()),
                    "recall": float(top[(gte == g) & (yte == 1)].sum() / max(1, ((gte == g) & (yte == 1)).sum()))}
                for g in ["F", "M"]}

    imp = pd.Series(gb.feature_importances_, index=datagen.FEATURES)
    cat_imp = imp.groupby(CATEGORY).sum().sort_values(ascending=False)

    bundle = {
        "model": gb,
        "metrics": {
            "auc": float(roc_auc_score(yte, p)),
            "auc_logistic_baseline": float(roc_auc_score(yte, p_lr)),
            "precision_at_top20": prec,
            "recall_at_top20": rec,
            "rule_baseline": {"precision": rule_prec, "recall": rule_rec, "flag_share": float(rule.mean())},
            "at_risk_rate": float(y.mean()),
            "train_students": int(cut), "test_students": int(n - cut),
            "fairness": fairness,
            "data": "synthetic (prototype)",
        },
        "importance": {CATEGORY_LABEL[k]: float(v) for k, v in cat_imp.items()},
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    return bundle


_bundle = None
_explainer = None


def load() -> dict:
    global _bundle, _explainer
    if _bundle is None:
        if not MODEL_PATH.exists():
            train()
        _bundle = joblib.load(MODEL_PATH)
        _explainer = shap.TreeExplainer(_bundle["model"])
    return _bundle


def _evidence(cat: str, r: pd.Series) -> str:
    if cat == "attendance":
        if r.att_drop > 0.03:
            return f"Attendance fell from {r.att_first4:.0%} to {r.att_last4:.0%}"
        return f"Attendance is low at {r.att_last4:.0%}"
    if cat == "marks_falling":
        if r.marks_drop > 1:
            return f"Average marks fell from {r.marks_first4:.0f} to {r.marks_last4:.0f}"
        return f"Average marks are only {r.marks_last4:.0f}"
    if cat == "low_marks":
        if r.n_below_pass > 0:
            return f"Weakest subject averages {r.min_subj_last4:.0f}; {int(r.n_below_pass)} subject(s) below 40"
        return f"Weakest subject averages {r.min_subj_last4:.0f}"
    if cat == "volatile":
        return f"Weekly scores swing by about {r.marks_vol:.0f} marks"
    if cat == "homework":
        if r.hw_drop > 0.05:
            return f"Homework on time fell from {r.hw_first4:.0%} to {r.hw_last4:.0%}"
        return f"Only {r.hw_last4:.0%} of homework submitted on time"
    if cat == "incidents":
        return f"{int(r.inc_last4)} behaviour incident(s) in the last 4 weeks"
    return ""


def score(X: pd.DataFrame) -> list[dict]:
    """Return risk, tier and top-3 explained reasons for each row of X."""
    b = load()
    p = b["model"].predict_proba(X)[:, 1]
    sv = _explainer.shap_values(X)
    if isinstance(sv, list):
        sv = sv[-1]
    sv = np.asarray(sv)
    out = []
    for i in range(len(X)):
        row = X.iloc[i]
        contrib: dict[str, float] = {}
        for j, f in enumerate(datagen.FEATURES):
            contrib[CATEGORY[f]] = contrib.get(CATEGORY[f], 0.0) + float(sv[i, j])
        pos = {k: v for k, v in contrib.items() if v > 0.05}
        total = sum(pos.values()) or 1.0
        reasons = [{"key": k, "label": CATEGORY_LABEL[k], "impact": round(v / total, 3),
                    "evidence": _evidence(k, row)}
                   for k, v in sorted(pos.items(), key=lambda kv: -kv[1])[:3]]
        out.append({"risk": float(p[i]), "tier": tier_for(float(p[i])), "reasons": reasons})
    return out


def info() -> dict:
    b = load()
    return {"metrics": b["metrics"], "importance": b["importance"], "trained_at": b["trained_at"],
            "features": datagen.FEATURES, "model": "GradientBoostingClassifier + SHAP",
            "thresholds": {"high": HIGH, "medium": MEDIUM}}
