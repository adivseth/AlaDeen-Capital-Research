"""Static charts rendered with matplotlib and embedded in the HTML report as base64 PNGs."""

from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from aladeen.quant.technicals import add_indicators

NAVY = "#1f3b73"
BLUE = "#2f6fdf"
TEAL = "#0f9d8a"
ORANGE = "#f08a24"
RED = "#d64545"
GREEN = "#2e9d4d"
GREY = "#8a94a6"
PURPLE = "#7b4bc4"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": "#c9d1de",
    "axes.grid": True, "grid.color": "#e8ecf3", "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
    "axes.titlesize": 10, "axes.titlecolor": NAVY, "legend.frameon": False, "legend.fontsize": 8,
})


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def technical_chart(prices: pd.DataFrame, title: str) -> str | None:
    """10-year 4-panel chart: price + 50/200 DMA + Bollinger, volume, RSI(14), MACD."""
    if prices is None or prices.empty or len(prices) < 60:
        return None
    df = add_indicators(prices)
    fig, axes = plt.subplots(4, 1, figsize=(11, 9.2), sharex=True,
                             gridspec_kw={"height_ratios": [3.2, 0.9, 1.1, 1.1], "hspace": 0.08})
    ax = axes[0]
    ax.plot(df.index, df["close"], color=NAVY, lw=1.0, label="Close")
    ax.plot(df.index, df["sma50"], color=ORANGE, lw=1.0, label="50-DMA")
    ax.plot(df.index, df["sma200"], color=TEAL, lw=1.2, label="200-DMA")
    ax.fill_between(df.index, df["bb_lower"], df["bb_upper"], color=BLUE, alpha=0.08, label="Bollinger (20,2)")
    ax.set_title(title, loc="left")
    ax.set_ylabel("₹")
    ax.legend(loc="upper left", ncol=4)
    if "volume" in df:
        colors = [GREEN if x >= 0 else RED for x in df["close"].diff().fillna(0)]
        axes[1].bar(df.index, df["volume"] / 1e5, color=colors, width=1.5, alpha=0.6)
        axes[1].set_ylabel("Vol (lakh)")
    axes[2].plot(df.index, df["rsi14"], color=PURPLE, lw=0.9)
    axes[2].axhline(70, color=RED, lw=0.7, ls="--")
    axes[2].axhline(30, color=GREEN, lw=0.7, ls="--")
    axes[2].set_ylim(0, 100)
    axes[2].set_ylabel("RSI 14")
    axes[3].plot(df.index, df["macd"], color=BLUE, lw=0.9, label="MACD")
    axes[3].plot(df.index, df["signal"], color=ORANGE, lw=0.9, label="Signal")
    axes[3].bar(df.index, df["hist"], color=[GREEN if h >= 0 else RED for h in df["hist"].fillna(0)],
                width=1.5, alpha=0.5)
    axes[3].set_ylabel("MACD")
    axes[3].legend(loc="upper left", ncol=2)
    axes[3].xaxis.set_major_locator(mdates.YearLocator())
    axes[3].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    return _png(fig)


def relative_chart(prices: pd.DataFrame, bench: pd.DataFrame, name: str, bench_name: str) -> str | None:
    if prices is None or prices.empty or bench is None or bench.empty:
        return None
    j = pd.concat([prices["close"], bench["close"]], axis=1, join="inner").dropna()
    if len(j) < 20:
        return None
    j = j / j.iloc[0] * 100
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.plot(j.index, j.iloc[:, 0], color=NAVY, lw=1.2, label=name)
    ax.plot(j.index, j.iloc[:, 1], color=ORANGE, lw=1.2, label=bench_name)
    ax.set_title(f"Relative performance, rebased to 100 ({j.index[0]:%b %Y})", loc="left")
    ax.legend(loc="upper left")
    return _png(fig)


def financials_chart(annual: pd.DataFrame) -> str | None:
    need = {"Revenue", "PAT"}
    if annual is None or annual.empty or not need.issubset(annual.columns):
        return None
    a = annual.dropna(subset=["Revenue"]).tail(10)
    fig, ax = plt.subplots(figsize=(11, 3.6))
    x = range(len(a))
    ax.bar([i - 0.2 for i in x], a["Revenue"], width=0.4, color=BLUE, label="Revenue (₹ Cr)")
    ax.bar([i + 0.2 for i in x], a["PAT"], width=0.4, color=TEAL, label="PAT (₹ Cr)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(a.index)
    ax.legend(loc="upper left")
    if "EBITDA margin %" in a:
        ax2 = ax.twinx()
        ax2.plot(list(x), a["EBITDA margin %"], color=ORANGE, marker="o", lw=1.6, label="EBITDA margin %")
        ax2.set_ylabel("Margin %")
        ax2.grid(False)
        ax2.spines["right"].set_visible(True)
        ax2.legend(loc="upper center")
    ax.set_title("Revenue, PAT and EBITDA margin (10 years)", loc="left")
    return _png(fig)


def scenario_chart(cmp_: float, scenarios: dict[str, float], target: float) -> str:
    fig, ax = plt.subplots(figsize=(7.5, 2.4))
    labels = ["Bear", "Base", "Bull"]
    vals = [scenarios.get("bear"), scenarios.get("base"), scenarios.get("bull")]
    ax.barh(labels, vals, color=[RED, BLUE, GREEN], alpha=0.85)
    ax.axvline(cmp_, color=NAVY, lw=1.5, ls="--", label=f"CMP ₹{cmp_:,.0f}")
    ax.axvline(target, color=ORANGE, lw=1.5, label=f"Target ₹{target:,.0f}")
    for i, v in enumerate(vals):
        if v is not None:
            ax.text(v, i, f"  ₹{v:,.0f}", va="center", fontsize=8)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0))
    ax.set_title("Scenario values per share", loc="left")
    return _png(fig)
