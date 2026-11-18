"""Intelligent features (pure Python, no ML dependency).

* TextAnalyzer           – tokenises, removes stop-words, light stemming and maps
                           synonyms ("down", "unavailable", "unable", "failing" → outage)
* SimilarityEngine       – cosine similarity over token vectors (+ service bonus)
* DuplicateDetector      – flags likely duplicates / related incidents
* CategoryClassifier     – suggests a category from keywords in the description
* ResolutionRecommender  – suggests past resolutions for similar incidents
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

STOPWORDS = frozenset("""
a an the is are was were be been being am i we you he she it they me my our your their to of
in on at for from by with and or but not no can cannot could would should will just this that
these those there here have has had do does did so as if than then when while again also any
some all very too please its it's im i'm get got getting since still now today anyone help
""".split())

# canonical concept ← surface words. Lets "payment app down" match "unable to pay".
SYNONYMS: dict[str, str] = {}
for canon, words in {
    "outage": "down unavailable unreachable unable failing fail failed failure fails broken "
              "crash crashed crashing error errors outage dead offline stopped timeout timing",
    "payment": "payment payments pay paying transaction transactions checkout billing invoice",
    "login": "login logon signin sign-in log password passwords authenticate authentication "
             "credential credentials sso mfa otp locked lockout",
    "network": "network wifi wi-fi internet lan vpn connectivity connection ethernet dns",
    "email": "email emails mail outlook inbox smtp",
    "slow": "slow slowness lag laggy latency sluggish hanging hang freeze frozen",
    "database": "database db sql query queries postgres mysql oracle table",
    "printer": "printer printing print scanner toner",
    "storage": "storage disk drive space quota sharepoint onedrive backup file files",
}.items():
    for w in words.split():
        SYNONYMS[w] = canon


class TextAnalyzer:
    _token = re.compile(r"[a-z0-9][a-z0-9\-]+")

    @staticmethod
    def _stem(w: str) -> str:
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > 4 and w.endswith(suf):
                return w[: -len(suf)]
        return w

    def tokens(self, text: str) -> list[str]:
        out = []
        for raw in self._token.findall((text or "").lower()):
            if raw in STOPWORDS:
                continue
            out.append(SYNONYMS.get(raw) or SYNONYMS.get(self._stem(raw)) or self._stem(raw))
        return out

    def vector(self, text: str) -> Counter:
        return Counter(self.tokens(text))


class SimilarityEngine:
    def __init__(self, analyzer: TextAnalyzer | None = None):
        self.analyzer = analyzer or TextAnalyzer()

    @staticmethod
    def cosine(a: Counter, b: Counter) -> float:
        if not a or not b:
            return 0.0
        dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb)

    def similarity(self, text_a: str, text_b: str) -> float:
        return self.cosine(self.analyzer.vector(text_a), self.analyzer.vector(text_b))


@dataclass
class Match:
    incident: object
    score: float
    link_type: str  # DUPLICATE | CORRELATED


class DuplicateDetector:
    """Score = text cosine + 0.25 if same affected service (capped at 1).
       ≥ DUPLICATE_THRESHOLD → likely duplicate; ≥ RELATED_THRESHOLD → related."""
    DUPLICATE_THRESHOLD = 0.55
    RELATED_THRESHOLD = 0.35
    SAME_SERVICE_BONUS = 0.25

    def __init__(self, engine: SimilarityEngine | None = None):
        self.engine = engine or SimilarityEngine()

    def score(self, title: str, description: str, service_id, other) -> float:
        s = self.engine.similarity(f"{title} {description}", f"{other.title} {other.description}")
        if service_id and other.service_id == service_id:
            s += self.SAME_SERVICE_BONUS
        return round(min(s, 1.0), 3)

    def find(self, title: str, description: str, service_id,
             candidates: Iterable, limit: int = 5) -> list[Match]:
        matches = []
        for other in candidates:
            s = self.score(title, description, service_id, other)
            if s >= self.DUPLICATE_THRESHOLD:
                matches.append(Match(other, s, "DUPLICATE"))
            elif s >= self.RELATED_THRESHOLD:
                matches.append(Match(other, s, "CORRELATED"))
        return sorted(matches, key=lambda m: -m.score)[:limit]


@dataclass
class CategorySuggestion:
    code: str
    name: str
    confidence: float
    matched: list[str]


class CategoryClassifier:
    """Keyword voting. Keywords are configured per category by the administrator,
    so new categories are learned without code changes."""

    def __init__(self, analyzer: TextAnalyzer | None = None):
        self.analyzer = analyzer or TextAnalyzer()

    def suggest(self, text: str, categories: Sequence) -> list[CategorySuggestion]:
        words = set(self.analyzer.tokens(text)) | set(re.findall(r"[a-z0-9]+", text.lower()))
        results = []
        for cat in categories:
            kws = {k.lower() for k in (cat.keywords or [])}
            kw_norm = {SYNONYMS.get(k, k) for k in kws} | kws
            hit = sorted(words & kw_norm)
            if hit:
                results.append(CategorySuggestion(cat.code, cat.name, len(hit), hit))
        total = sum(r.confidence for r in results) or 1
        for r in results:
            r.confidence = round(r.confidence / total, 2)
        return sorted(results, key=lambda r: -r.confidence)


class ResolutionRecommender:
    def __init__(self, engine: SimilarityEngine | None = None, min_score: float = 0.3):
        self.engine = engine or SimilarityEngine()
        self.min_score = min_score

    def recommend(self, text: str, resolved: Iterable, limit: int = 3):
        scored = []
        for inc in resolved:
            s = self.engine.similarity(text, f"{inc.title} {inc.description}")
            if s >= self.min_score:
                scored.append((inc, round(s, 3)))
        return sorted(scored, key=lambda x: -x[1])[:limit]
