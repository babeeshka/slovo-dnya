"""
study.py — Spaced repetition system using SM-2 algorithm.

The SM-2 algorithm calculates optimal review intervals based on recall quality.
Words are reviewed at increasing intervals as they become better memorized.

Quality ratings (0-5):
    0: Complete blackout - no recall
    1: Incorrect response, correct recalled on hint
    2: Incorrect response, correct recalled with difficulty
    3: Correct response, but with difficulty
    4: Correct response, with hesitation
    5: Perfect response, immediate recall

Algorithm parameters:
    - ease_factor: Multiplier for interval calculation (default 2.5)
    - interval: Days until next review (default 0)
    - next_review: Date of next scheduled review
    - review_count: Total number of reviews performed
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from slovo.db import words_col


DEFAULT_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3


def calculate_next_review(
    quality: int,
    current_ease_factor: float,
    current_interval: int,
    review_count: int,
) -> tuple[float, int, datetime]:
    """
    Calculate next review parameters using SM-2 algorithm.

    Args:
        quality: User's recall quality (0-5)
        current_ease_factor: Current ease factor for the word
        current_interval: Current interval in days
        review_count: Number of times word has been reviewed

    Returns:
        Tuple of (new_ease_factor, new_interval_days, next_review_datetime)

    SM-2 algorithm logic:
        - Quality < 3: Reset interval to 0, schedule immediate review
        - Quality >= 3: Increase interval based on ease factor
        - Ease factor adjusts based on quality (harder = lower, easier = higher)
    """
    if not 0 <= quality <= 5:
        raise ValueError(f"Quality must be between 0 and 5, got {quality}")

    # Calculate new ease factor
    # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ease_factor = current_ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    # Ensure ease factor doesn't go below minimum
    if ease_factor < MIN_EASE_FACTOR:
        ease_factor = MIN_EASE_FACTOR

    # Calculate new interval
    if quality < 3:
        # Failed recall - restart from beginning
        interval_days = 0
    elif review_count == 0:
        # First successful review - 1 day
        interval_days = 1
    elif review_count == 1:
        # Second successful review - 6 days
        interval_days = 6
    else:
        # Subsequent reviews - multiply previous interval by ease factor
        interval_days = int(current_interval * ease_factor)

    # Calculate next review date
    next_review = datetime.now(timezone.utc) + timedelta(days=interval_days)

    return ease_factor, interval_days, next_review


def record_review(lemma: str, quality: int) -> dict:
    """
    Record a review for a word and update spaced repetition data.

    Args:
        lemma: The word being reviewed
        quality: User's recall quality (0-5)

    Returns:
        Dictionary with updated word data including:
            - ease_factor
            - interval
            - next_review
            - review_count

    Raises:
        ValueError: If quality is not in range 0-5
        RuntimeError: If word not found in database
    """
    if not 0 <= quality <= 5:
        raise ValueError(f"Quality must be between 0 and 5, got {quality}")

    word = words_col().find_one({"lemma": lemma.lower()})
    if not word:
        raise RuntimeError(f"Word not found in database: {lemma}")

    # Get current spaced repetition data (with defaults)
    current_ease = word.get("ease_factor", DEFAULT_EASE_FACTOR)
    current_interval = word.get("interval", 0)
    current_review_count = word.get("review_count", 0)

    # Calculate new values
    new_ease, new_interval, next_review = calculate_next_review(
        quality=quality,
        current_ease_factor=current_ease,
        current_interval=current_interval,
        review_count=current_review_count,
    )

    # Update database
    update_data = {
        "ease_factor": new_ease,
        "interval": new_interval,
        "next_review": next_review,
        "review_count": current_review_count + 1,
        "last_reviewed": datetime.now(timezone.utc),
    }

    words_col().update_one(
        {"lemma": lemma.lower()},
        {"$set": update_data}
    )

    return {
        "lemma": lemma,
        "quality": quality,
        "ease_factor": new_ease,
        "interval": new_interval,
        "next_review": next_review,
        "review_count": current_review_count + 1,
    }


def get_due_words(limit: int = 10) -> list[dict]:
    """
    Get words that are due for review.

    Args:
        limit: Maximum number of words to return

    Returns:
        List of word documents sorted by:
            1. Never reviewed (next_review is None)
            2. Overdue (next_review in the past)
            3. Review count (prioritize less-reviewed words)
    """
    now = datetime.now(timezone.utc)

    # Words are due if:
    # 1. Never reviewed (next_review is None or missing)
    # 2. Next review date has passed
    # 3. Not marked as known (known words are excluded from study)
    query = {
        "known": {"$ne": True},
        "$or": [
            {"next_review": None},
            {"next_review": {"$exists": False}},
            {"next_review": {"$lte": now}},
        ]
    }

    # Sort priority:
    # 1. Words never reviewed first (review_count missing or 0)
    # 2. Then by next_review date (oldest first)
    # 3. Then by frequency (most common first)
    pipeline = [
        {"$match": query},
        {"$addFields": {
            "review_count_safe": {"$ifNull": ["$review_count", 0]},
            "next_review_safe": {"$ifNull": ["$next_review", datetime.min.replace(tzinfo=timezone.utc)]},
        }},
        {"$sort": {
            "review_count_safe": 1,
            "next_review_safe": 1,
            "frequency": -1,
        }},
        {"$limit": limit},
    ]

    return list(words_col().aggregate(pipeline))


def get_study_stats() -> dict:
    """
    Get statistics about the user's study progress.

    Returns:
        Dictionary containing:
            - total_words: Total words in corpus
            - words_due: Number of words due for review
            - words_learning: Words in active study (reviewed at least once)
            - words_mastered: Words with high ease factor and long intervals
            - average_ease_factor: Average ease across all reviewed words
            - total_reviews: Total number of reviews performed
    """
    wcol = words_col()
    now = datetime.now(timezone.utc)

    total_words = wcol.count_documents({})

    # Words due for review
    words_due = wcol.count_documents({
        "known": {"$ne": True},
        "$or": [
            {"next_review": None},
            {"next_review": {"$exists": False}},
            {"next_review": {"$lte": now}},
        ]
    })

    # Words in active learning (reviewed at least once, not known)
    words_learning = wcol.count_documents({
        "known": {"$ne": True},
        "review_count": {"$gte": 1},
    })

    # Words considered mastered (ease >= 2.5, interval >= 30 days)
    words_mastered = wcol.count_documents({
        "ease_factor": {"$gte": 2.5},
        "interval": {"$gte": 30},
    })

    # Calculate average ease factor for words that have been reviewed
    pipeline = [
        {"$match": {"review_count": {"$gte": 1}}},
        {"$group": {
            "_id": None,
            "avg_ease": {"$avg": "$ease_factor"},
            "total_reviews": {"$sum": "$review_count"},
        }},
    ]
    stats_result = list(wcol.aggregate(pipeline))

    avg_ease = 0.0
    total_reviews = 0
    if stats_result:
        avg_ease = stats_result[0].get("avg_ease", 0.0)
        total_reviews = stats_result[0].get("total_reviews", 0)

    return {
        "total_words": total_words,
        "words_due": words_due,
        "words_learning": words_learning,
        "words_mastered": words_mastered,
        "average_ease_factor": round(avg_ease, 2) if avg_ease else 0.0,
        "total_reviews": total_reviews,
    }


def get_word_study_data(lemma: str) -> Optional[dict]:
    """
    Get spaced repetition data for a specific word.

    Args:
        lemma: The word to look up

    Returns:
        Dictionary with word's study data or None if word not found
    """
    word = words_col().find_one(
        {"lemma": lemma.lower()},
        {
            "lemma": 1,
            "translation": 1,
            "pos": 1,
            "ease_factor": 1,
            "interval": 1,
            "next_review": 1,
            "review_count": 1,
            "last_reviewed": 1,
        }
    )

    if not word:
        return None

    return {
        "lemma": word["lemma"],
        "translation": word.get("translation", ""),
        "pos": word.get("pos", ""),
        "ease_factor": word.get("ease_factor", DEFAULT_EASE_FACTOR),
        "interval": word.get("interval", 0),
        "next_review": word.get("next_review"),
        "review_count": word.get("review_count", 0),
        "last_reviewed": word.get("last_reviewed"),
    }
