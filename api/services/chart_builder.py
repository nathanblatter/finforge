"""Matplotlib chart builders for FinForge PDF reports."""

import io
from datetime import date
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.figure import Figure

# FinForge color palette
COLORS = {
    "sky": "#0ea5e9",
    "green": "#34d399",
    "red": "#f87171",
    "purple": "#818cf8",
    "orange": "#fb923c",
    "pink": "#f472b6",
    "lavender": "#a78bfa",
    "yellow": "#fbbf24",
    "teal": "#2dd4bf",
    "blue": "#60a5fa",
}

PALETTE = list(COLORS.values())

_COMMON = dict(
    facecolor="white",
    edgecolor="none",
)


def _currency_fmt(x: float, _=None) -> str:
    if abs(x) >= 1000:
        return f"${x:,.0f}"
    return f"${x:,.2f}"


def spending_pie_chart(categories: dict[str, float], title: str = "Spending by Category") -> Figure:
    fig, ax = plt.subplots(figsize=(6, 4), subplot_kw=dict(aspect="equal"), **_COMMON)
    labels = list(categories.keys())
    values = list(categories.values())
    colors = PALETTE[: len(labels)]

    wedges, texts, autotexts = ax.pie(
        values, labels=None, autopct="%1.1f%%", colors=colors,
        startangle=90, pctdistance=0.75,
        textprops=dict(fontsize=8, color="#334155"),
    )
    ax.legend(
        wedges, [f"{l} ({_currency_fmt(v)})" for l, v in zip(labels, values)],
        loc="center left", bbox_to_anchor=(1, 0.5), fontsize=7, frameon=False,
    )
    ax.set_title(title, fontsize=11, fontweight="bold", color="#1e293b", pad=12)
    fig.tight_layout()
    return fig


def spending_trend_bar(
    months: list[str],
    category_totals: dict[str, list[float]],
    title: str = "Spending Trend",
) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4), **_COMMON)
    x = range(len(months))
    bottom = [0.0] * len(months)
    cats = list(category_totals.keys())

    for i, cat in enumerate(cats):
        vals = category_totals[cat]
        ax.bar(x, vals, bottom=bottom, label=cat, color=PALETTE[i % len(PALETTE)], width=0.6)
        bottom = [b + v for b, v in zip(bottom, vals)]

    ax.set_xticks(list(x))
    ax.set_xticklabels(months, fontsize=8, color="#64748b")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_currency_fmt))
    ax.tick_params(axis="y", labelsize=8, labelcolor="#64748b")
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    ax.set_title(title, fontsize=11, fontweight="bold", color="#1e293b", pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e2e8f0")
    ax.spines["bottom"].set_color("#e2e8f0")
    fig.tight_layout()
    return fig


def net_worth_line(
    dates: list[date],
    values: list[float],
    title: str = "Net Worth Trend",
) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 3.5), **_COMMON)
    ax.fill_between(dates, values, alpha=0.15, color=COLORS["sky"])
    ax.plot(dates, values, color=COLORS["sky"], linewidth=2)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_currency_fmt))
    ax.tick_params(axis="both", labelsize=8, labelcolor="#64748b")
    ax.set_title(title, fontsize=11, fontweight="bold", color="#1e293b", pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e2e8f0")
    ax.spines["bottom"].set_color("#e2e8f0")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def income_vs_expenses_bar(
    months: list[str],
    income: list[float],
    expenses: list[float],
    title: str = "Income vs Expenses",
) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4), **_COMMON)
    x = range(len(months))
    w = 0.35
    ax.bar([i - w / 2 for i in x], income, w, label="Income", color=COLORS["green"])
    ax.bar([i + w / 2 for i in x], expenses, w, label="Expenses", color=COLORS["red"])
    ax.set_xticks(list(x))
    ax.set_xticklabels(months, fontsize=8, color="#64748b")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_currency_fmt))
    ax.tick_params(axis="y", labelsize=8, labelcolor="#64748b")
    ax.legend(fontsize=8, frameon=False)
    ax.set_title(title, fontsize=11, fontweight="bold", color="#1e293b", pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e2e8f0")
    ax.spines["bottom"].set_color("#e2e8f0")
    fig.tight_layout()
    return fig


def contribution_timeline(
    dates: list[date],
    amounts: list[float],
    cumulative: list[float],
    limit: Optional[float] = None,
    title: str = "Contribution Timeline",
) -> Figure:
    fig, ax1 = plt.subplots(figsize=(8, 4), **_COMMON)
    ax1.bar(dates, amounts, color=COLORS["purple"], width=2, alpha=0.7, label="Contribution")
    ax1.set_ylabel("Per Transfer", fontsize=8, color="#64748b")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_currency_fmt))
    ax1.tick_params(axis="both", labelsize=8, labelcolor="#64748b")

    ax2 = ax1.twinx()
    ax2.plot(dates, cumulative, color=COLORS["sky"], linewidth=2, label="Cumulative")
    if limit:
        ax2.axhline(y=limit, color=COLORS["red"], linestyle="--", linewidth=1, alpha=0.7, label=f"Limit (${limit:,.0f})")
    ax2.set_ylabel("Cumulative", fontsize=8, color="#64748b")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_currency_fmt))
    ax2.tick_params(axis="y", labelsize=8, labelcolor="#64748b")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=7, frameon=False, loc="upper left")

    ax1.set_title(title, fontsize=11, fontweight="bold", color="#1e293b", pad=12)
    ax1.spines["top"].set_visible(False)
    for ax in (ax1, ax2):
        ax.spines["left"].set_color("#e2e8f0")
        ax.spines["bottom"].set_color("#e2e8f0")
    ax2.spines["right"].set_color("#e2e8f0")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig
