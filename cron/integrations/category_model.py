"""
ML merchant→category classifier for FinForge.

Trains a TF-IDF (word + char n-gram) + LogisticRegression pipeline on the
user's own labeled transactions, then backfills categories for transactions
the rule-based mappers left as "Other". Manual overrides and explicit
merchant rules always win — the model only ever fills gaps.

Model persisted to /secrets/category_model.pkl.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone

import joblib

from db import TransactionRow, get_session

logger = logging.getLogger("finforge.cron.category_model")

MODEL_PATH = "/secrets/category_model.pkl"
META_PATH = "/secrets/category_model_meta.json"

MIN_SAMPLES = 100          # total labeled rows needed to bother training
MIN_CLASS_SAMPLES = 5      # drop categories with fewer examples
CONFIDENCE_THRESHOLD = 0.60
SKIP_CATEGORIES = frozenset({"Other", "Investment Transfer"})


def _labeled_data() -> tuple[list[str], list[str]]:
    """(merchant names, categories) for all confidently-labeled transactions."""
    with get_session() as session:
        rows = (
            session.query(TransactionRow.merchant_name, TransactionRow.category)
            .filter(
                TransactionRow.merchant_name.isnot(None),
                TransactionRow.category.isnot(None),
                TransactionRow.category.notin_(SKIP_CATEGORIES),
            )
            .all()
        )
    texts = [m.strip().lower() for m, _c in rows if m and m.strip()]
    labels = [c for m, c in rows if m and m.strip()]
    return texts, labels


def train_category_model() -> None:
    """Train and persist the classifier. Skips quietly on insufficient data."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import FeatureUnion, Pipeline

    texts, labels = _labeled_data()

    # Drop ultra-rare classes — they only add noise
    counts = Counter(labels)
    keep = {c for c, n in counts.items() if n >= MIN_CLASS_SAMPLES}
    pairs = [(t, l) for t, l in zip(texts, labels) if l in keep]

    if len(pairs) < MIN_SAMPLES or len(keep) < 2:
        logger.info(
            "[category_model] Insufficient training data (%d rows, %d classes) — skipping",
            len(pairs), len(keep),
        )
        return

    X = [t for t, _ in pairs]
    y = [l for _, l in pairs]

    pipeline = Pipeline([
        ("tfidf", FeatureUnion([
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2)),
        ])),
        ("clf", LogisticRegression(max_iter=1000, C=5.0, class_weight="balanced")),
    ])

    cv_folds = min(5, min(Counter(y).values()))
    accuracy = None
    if cv_folds >= 2:
        try:
            scores = cross_val_score(pipeline, X, y, cv=cv_folds, scoring="accuracy")
            accuracy = round(float(scores.mean()), 4)
        except Exception as exc:
            logger.warning("[category_model] Cross-validation failed: %s", exc)

    pipeline.fit(X, y)
    joblib.dump(pipeline, MODEL_PATH)

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(X),
        "classes": sorted(keep),
        "cv_accuracy": accuracy,
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(
        "[category_model] Trained on %d rows, %d classes, cv_accuracy=%s",
        len(X), len(keep), accuracy,
    )

    apply_model_suggestions()


def apply_model_suggestions() -> None:
    """Recategorize 'Other'/uncategorized transactions the model is confident about.

    Never touches overridden transactions; does not set category_overridden,
    so a future better rule or override can still change them.
    """
    try:
        model = joblib.load(MODEL_PATH)
    except FileNotFoundError:
        logger.info("[category_model] No trained model — skipping suggestions")
        return
    except Exception as exc:
        logger.error("[category_model] Failed to load model: %s", exc)
        return

    with get_session() as session:
        candidates = (
            session.query(TransactionRow)
            .filter(
                TransactionRow.category_overridden.is_(False),
                TransactionRow.merchant_name.isnot(None),
                (TransactionRow.category.is_(None)) | (TransactionRow.category == "Other"),
            )
            .all()
        )
        if not candidates:
            logger.info("[category_model] No uncategorized transactions to score")
            return

        texts = [t.merchant_name.strip().lower() for t in candidates]
        try:
            probas = model.predict_proba(texts)
        except Exception as exc:
            logger.error("[category_model] Inference failed: %s", exc)
            return
        classes = model.classes_

        updated = 0
        for t, p in zip(candidates, probas):
            best = int(p.argmax())
            if p[best] >= CONFIDENCE_THRESHOLD:
                t.category = str(classes[best])
                updated += 1

        logger.info(
            "[category_model] Scored %d uncategorized transactions, recategorized %d (>= %.0f%% confidence)",
            len(candidates), updated, CONFIDENCE_THRESHOLD * 100,
        )
