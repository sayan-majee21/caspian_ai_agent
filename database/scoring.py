"""Project scoring and Bayesian average calculation module."""

import math


def calculate_bayesian_average(
    ratings: list[int], C: float = 5.0, m: float = 5.0
) -> float:
    """Calculate the Bayesian average of community ratings.

    Args:
        ratings (list[int]): List of integer ratings (1 to 10 scale).
        C (float): Weight of prior confidence. Default is 5.0.
        m (float): Prior mean rating (1 to 10 scale). Default is 5.0.

    Returns:
        float: Calculated Bayesian average on a 1-10 scale.
    """
    valid_ratings = [
        r for r in ratings
        if isinstance(r, (int, float)) and not math.isnan(r) and not math.isinf(r) and 1 <= r <= 10
    ]
    if not valid_ratings:
        return m
    n = len(valid_ratings)
    sum_ratings = sum(valid_ratings)
    return (C * m + sum_ratings) / (C + n)


def calculate_final_score(
    ai_score: float | None, ratings: list[int]
) -> float:
    """Calculate the overall final score for a project.

    Combines the AI score (0-100 scale, weighted at 70%) and the Bayesian average
    of community ratings (scaled from 1-10 to 0-100, weighted at 30%).

    Args:
        ai_score (float | None): AI evaluation score (0-100 scale). Defaults to 0.0 if None.
        ratings (list[int]): List of 1-10 community ratings.

    Returns:
        float: Final score normalized to a 0-100 scale, rounded to 2 decimal places.
    """
    if ai_score is None or math.isnan(ai_score) or math.isinf(ai_score):
        ai_val = 0.0
    else:
        ai_val = max(0.0, min(100.0, float(ai_score)))

    bayesian_avg_raw = calculate_bayesian_average(ratings)
    bayesian_avg_scaled = bayesian_avg_raw * 10.0  # Normalize 1-10 scale to 0-100
    final_score = (ai_val * 0.7) + (bayesian_avg_scaled * 0.3)
    return round(final_score, 2)
