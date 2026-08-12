"""Project scoring and Bayesian average calculation module."""


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
    if not ratings:
        return m
    n = len(ratings)
    sum_ratings = sum(ratings)
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
    ai_val = ai_score if ai_score is not None else 0.0
    bayesian_avg_raw = calculate_bayesian_average(ratings)
    bayesian_avg_scaled = bayesian_avg_raw * 10.0  # Normalize 1-10 scale to 0-100
    final_score = (ai_val * 0.7) + (bayesian_avg_scaled * 0.3)
    return round(final_score, 2)
