"""Interactive Plotly charts and visual telemetry widgets for TalentCaspian."""

from typing import Any
import pandas as pd
import plotly.graph_objects as go


def _get_theme_layout(title: str = "", height: int = 280) -> dict[str, Any]:
    """Base layout template for sleek dark-themed charts.

    Args:
        title (str): Chart title.
        height (int): Chart height in pixels.

    Returns:
        dict[str, Any]: Plotly layout dictionary.
    """
    return {
        "title": {
            "text": title,
            "font": {"family": "Inter, sans-serif", "size": 15, "color": "#F8FAFC"},
            "x": 0.02,
        },
        "paper_bgcolor": "rgba(15, 23, 42, 0.0)",
        "plot_bgcolor": "rgba(15, 23, 42, 0.0)",
        "margin": {"l": 20, "r": 20, "t": 40, "b": 20},
        "height": height,
        "font": {"family": "Inter, sans-serif", "color": "#94A3B8"},
        "showlegend": True,
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 11, "color": "#CBD5E1"},
        },
    }


def create_score_gauge(
    score: float | None,
    title: str = "Composite AI Score",
    subtitle: str = "Evaluated via Gemini Code Intelligence",
) -> go.Figure:
    """Create a modern circular gauge ring for AI score.

    Args:
        score (float | None): Composite score (0-100).
        title (str): Primary gauge title.
        subtitle (str): Explanatory subtitle.

    Returns:
        go.Figure: Plotly indicator figure.
    """
    val = float(score) if score is not None else 0.0

    if val >= 80:
        bar_color = "#10B981"  # Emerald
    elif val >= 60:
        bar_color = "#38BDF8"  # Sky Blue
    else:
        bar_color = "#F59E0B"  # Amber

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=val,
            number={"suffix": "/100", "font": {"size": 36, "color": "#F8FAFC", "family": "Inter, sans-serif"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#475569", "tickfont": {"size": 10}},
                "bar": {"color": bar_color, "thickness": 0.28},
                "bgcolor": "rgba(30, 41, 59, 0.5)",
                "borderwidth": 1,
                "bordercolor": "rgba(51, 65, 85, 0.6)",
                "steps": [
                    {"range": [0, 60], "color": "rgba(245, 158, 11, 0.08)"},
                    {"range": [60, 80], "color": "rgba(56, 189, 248, 0.08)"},
                    {"range": [80, 100], "color": "rgba(16, 185, 129, 0.12)"},
                ],
                "threshold": {
                    "line": {"color": "#10B981", "width": 3},
                    "thickness": 0.75,
                    "value": 85,
                },
            },
            title={
                "text": f"<b>{title}</b><br><span style='font-size:0.8em;color:#94A3B8'>{subtitle}</span>",
                "font": {"size": 14, "color": "#E2E8F0"},
            },
        )
    )

    layout = _get_theme_layout("", height=240)
    layout["margin"] = {"l": 25, "r": 25, "t": 35, "b": 10}
    fig.update_layout(**layout)
    return fig


def create_score_breakdown_bars(metrics: list[dict[str, Any]]) -> go.Figure:
    """Create a sleek horizontal contribution bar chart for component metrics.

    Args:
        metrics (list[dict[str, Any]]): List of dicts with 'name' and 'score' keys.

    Returns:
        go.Figure: Plotly bar chart figure.
    """
    if not metrics:
        metrics = [
            {"name": "Technical Quality (40%)", "score": 0.0},
            {"name": "Code Authenticity (30%)", "score": 0.0},
            {"name": "Project Creativity (30%)", "score": 0.0},
        ]

    def _safe_float(val: Any) -> float:
        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    names = [m.get("name", "Metric") for m in metrics]
    scores = [_safe_float(m.get("score")) for m in metrics]

    colors = []
    for s in scores:
        if s >= 80:
            colors.append("#10B981")
        elif s >= 60:
            colors.append("#38BDF8")
        else:
            colors.append("#F59E0B")

    fig = go.Figure(
        go.Bar(
            x=scores,
            y=names,
            orientation="h",
            marker=dict(
                color=colors,
                line=dict(color="rgba(255, 255, 255, 0.15)", width=1),
            ),
            text=[f"{s:.1f}/100" for s in scores],
            textposition="auto",
        )
    )

    layout = _get_theme_layout("Metric Breakdown", height=240)
    layout["xaxis"] = dict(
        range=[0, 105],
        showgrid=True,
        gridcolor="rgba(51, 65, 85, 0.4)",
        zeroline=False,
    )
    layout["yaxis"] = dict(autorange="reversed")
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


def create_rating_timeline_chart(ratings: list[dict[str, Any]]) -> go.Figure:
    """Create rating trajectory spline chart comparing peer community vs recruiter evaluations.

    Args:
        ratings (list[dict[str, Any]]): List of timestamped rating records.

    Returns:
        go.Figure: Plotly line chart figure.
    """
    if not ratings:
        fig = go.Figure()
        fig.add_annotation(
            text="No community or recruiter ratings recorded yet.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=13, color="#64748B"),
        )
        layout = _get_theme_layout("Rating Evolution & Trajectory", height=250)
        fig.update_layout(**layout)
        return fig

    df = pd.DataFrame(ratings)
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
    else:
        df["created_at"] = pd.Timestamp.now()
    if "rater_type" not in df.columns:
        df["rater_type"] = "public"
    if "rating" not in df.columns:
        df["rating"] = 5.0
    df = df.sort_values("created_at")

    fig = go.Figure()

    peer_df = df[df["rater_type"] != "recruiter"]
    if not peer_df.empty:
        fig.add_trace(
            go.Scatter(
                x=peer_df["created_at"],
                y=peer_df["rating"],
                mode="lines+markers",
                name="Peer Community",
                line=dict(color="#38BDF8", width=2, shape="spline"),
                marker=dict(size=7, color="#38BDF8", symbol="circle"),
            )
        )

    recruiter_df = df[df["rater_type"] == "recruiter"]
    if not recruiter_df.empty:
        fig.add_trace(
            go.Scatter(
                x=recruiter_df["created_at"],
                y=recruiter_df["rating"],
                mode="lines+markers",
                name="Recruiters",
                line=dict(color="#A855F7", width=2.5, dash="dot"),
                marker=dict(size=8, color="#C084FC", symbol="diamond"),
            )
        )

    layout = _get_theme_layout("Rating Evolution & Trajectory", height=260)
    layout["yaxis"] = dict(
        range=[0, 10.5],
        dtick=2,
        showgrid=True,
        gridcolor="rgba(51, 65, 85, 0.4)",
        title=dict(text="Score (1-10)", font=dict(size=11)),
    )
    layout["xaxis"] = dict(
        showgrid=False,
        tickfont=dict(size=10, color="#64748B"),
    )
    fig.update_layout(**layout)
    return fig


def create_commit_activity_chart(commits: list[dict[str, Any]]) -> go.Figure:
    """Create commit activity and change classification chart.

    Args:
        commits (list[dict[str, Any]]): Commit logs list.

    Returns:
        go.Figure: Plotly activity chart.
    """
    if not commits:
        fig = go.Figure()
        fig.add_annotation(
            text="No repository commits logged yet via GitHub Webhooks.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=13, color="#64748B"),
        )
        layout = _get_theme_layout("Commit Evolution & Change Classification", height=240)
        fig.update_layout(**layout)
        return fig

    df = pd.DataFrame(commits)
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
    else:
        df["created_at"] = pd.Timestamp.now()
    df = df.sort_values("created_at")

    # Group by classification
    if "change_classification" not in df.columns:
        df["change_classification"] = "minor"
    classifications = df["change_classification"].fillna("minor").astype(str).str.lower()
    major_count = int((classifications == "major").sum())
    minor_count = int((classifications == "minor").sum())

    fig = go.Figure(
        go.Bar(
            x=["Major Updates", "Minor / Fix Commits"],
            y=[major_count, minor_count],
            marker=dict(
                color=["#10B981", "#64748B"],
                line=dict(color="rgba(255, 255, 255, 0.2)", width=1),
            ),
            text=[f"{major_count} pushes", f"{minor_count} pushes"],
            textposition="auto",
        )
    )

    layout = _get_theme_layout("Commit Evolution & Change Classification", height=240)
    layout["yaxis"] = dict(
        showgrid=True,
        gridcolor="rgba(51, 65, 85, 0.4)",
        title=dict(text="Push Count", font=dict(size=11)),
    )
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


def create_recruiter_demand_chart(matching_recruiters: int, total_pool: int = 10) -> go.Figure:
    """Create recruiter market fit and talent demand indicator.

    Args:
        matching_recruiters (int): Count of matching recruiters.
        total_pool (int): Total active recruiter pool size.

    Returns:
        go.Figure: Plotly market demand indicator.
    """
    fit_pct = min(100.0, (matching_recruiters / max(1, total_pool)) * 100.0)

    fig = go.Figure(
        go.Indicator(
            mode="number+gauge",
            value=matching_recruiters,
            number={"suffix": " Recruiters", "font": {"size": 28, "color": "#38BDF8"}},
            title={"text": "<b>Active Recruiter Matches</b>", "font": {"size": 13, "color": "#E2E8F0"}},
            gauge={
                "axis": {"range": [0, max(10, total_pool)], "tickfont": {"size": 9}},
                "bar": {"color": "#38BDF8", "thickness": 0.3},
                "bgcolor": "rgba(30, 41, 59, 0.4)",
                "steps": [
                    {"range": [0, 3], "color": "rgba(100, 116, 139, 0.1)"},
                    {"range": [3, 7], "color": "rgba(56, 189, 248, 0.15)"},
                    {"range": [7, max(10, total_pool)], "color": "rgba(16, 185, 129, 0.2)"},
                ],
            },
        )
    )
    layout = _get_theme_layout("", height=180)
    layout["margin"] = {"l": 15, "r": 15, "t": 25, "b": 10}
    fig.update_layout(**layout)
    return fig
