#!/usr/bin/env python3
"""Generate the 10 thesis charts as matplotlib PNGs into dashboard/assets/.

Reads ONLY data/processed/chart_0*_data.json (+ metrics.json / dcf.json for
annotations). No network, no re-fetching — the dashboard agent can reuse the
same JSONs to render tables.

Usage: python3 src/charts.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parent.parent
PROC = REPO / "data" / "processed"
OUT = REPO / "dashboard" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

NEAR_GREEN = "#00C08B"
NEAR_DARK = "#1a1a1a"
GREY = "#8a8a8a"
BLUE = "#4A90D9"
ORANGE = "#E8833A"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": "#cccccc", "axes.grid": True,
    "grid.color": "#e8e8e8", "grid.linewidth": 0.7,
    "axes.axisbelow": True, "figure.dpi": 150,
})


def load(name):
    return json.loads((PROC / name).read_text())


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    # SVG twin: UTF-8 text, so the charts can be published through
    # text-only push tooling (GitHub push_files rejects binary PNGs).
    # Same figure, same numbers — only the container differs.
    svg_name = name.rsplit(".", 1)[0] + ".svg"
    fig.savefig(OUT / svg_name, format="svg")
    plt.close(fig)
    print(f"wrote dashboard/assets/{name} + {svg_name}")


def style_ax(ax, title, xlabel="", ylabel=""):
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left", pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)


def chart01():
    d = load("chart_01_data.json")
    dates = np.array([np.datetime64(x) for x in d["dates"]])
    fees = np.array(d["daily_fees_usd"], dtype=float)
    ma = np.array(d["ma30_usd"], dtype=float)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, fees, color=GREY, lw=0.6, alpha=0.6, label="Daily fees")
    ax.plot(dates, ma, color=NEAR_GREEN, lw=2, label="30-day moving average")
    ax.set_yscale("log")
    style_ax(ax, "NEAR Intents daily fees — the compounding revenue curve",
             ylabel="USD / day (log scale)")
    ax.legend(frameon=False, loc="upper left")
    ax.text(0.01, 0.02,
            f"Source: DefiLlama near-intents, {len(dates)} daily points "
            f"({d['dates'][0]} to {d['dates'][-1]}). 30d fees: "
            f"{sum(fees[-30:]):,.0f} USD.",
            transform=ax.transAxes, fontsize=8, color=GREY)
    # linear inset
    axins = ax.inset_axes([0.55, 0.55, 0.42, 0.38])
    axins.plot(dates, fees, color=GREY, lw=0.5, alpha=0.6)
    axins.plot(dates, ma, color=NEAR_GREEN, lw=1.5)
    axins.set_title("Same data, linear scale", fontsize=9)
    axins.tick_params(labelsize=7)
    save(fig, "chart01_intents_daily_fees.png")


def chart02():
    d = load("chart_02_data.json")
    dates = np.array([np.datetime64(x) for x in d["dates"]])
    inten = np.array(d["intents_daily_fees_usd"], dtype=float)
    base_d = d["base_daily_fees_usd"]
    base_dates = np.array([np.datetime64(x) for x in d["base_dates"]])
    # base series may be shorter / different dates; align by tail if needed
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, inten, color=NEAR_GREEN, lw=1.2, label="NEAR Intents fees")
    if base_d:
        bd = np.array(base_d, dtype=float)
        ax.plot(base_dates, bd, color=ORANGE, lw=1.2,
                label="NEAR base-chain (gas) fees")
    ax.set_yscale("log")
    style_ax(ax, "Gas is dead — Intents is the business",
             ylabel="USD / day (log scale)")
    ax.legend(frameon=False, loc="upper left")
    ax.text(0.01, 0.02,
            f"Intents 30d fees: {d['intents_30d_usd']:,.0f} USD vs base-chain "
            f"24h fees: {d['base_24h_usd']:,.0f} USD. Source: DefiLlama.",
            transform=ax.transAxes, fontsize=8, color=GREY)
    save(fig, "chart02_intents_vs_base_fees.png")


def chart03():
    d = load("chart_03_data.json")
    dates = np.array([np.datetime64(x) for x in d["dates"]])
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, d["price_indexed"], color=BLUE, lw=1.8, label="NEAR price")
    ax.plot(dates, d["trailing_30d_fees_indexed"], color=NEAR_GREEN, lw=1.8,
            label="Trailing-30d Intents fees")
    ax.axhline(100, color=GREY, lw=0.8, ls="--")
    style_ax(ax, "Price tracks fees over the year — both fell hard in the last 30 days",
             ylabel="Indexed to 100 at start")
    ax.legend(frameon=False, loc="upper left")
    ax.text(0.01, 0.02,
            f"365d: price {d['price_change_pct']:+.1f}%, trailing-30d fees "
            f"{d['fees_change_pct']:+.1f}%. Last 30d: price "
            f"{d['price_30d_change_pct']:+.1f}%, fees "
            f"{d['fees_30d_change_pct']:+.1f}%. "
            "Sources: CoinGecko (price) + DefiLlama (fees).",
            transform=ax.transAxes, fontsize=8, color=GREY)
    save(fig, "chart03_price_vs_fees_divergence.png")


def chart04():
    d = load("chart_04_data.json")
    labels, values = d["labels"], d["values"]
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = [NEAR_GREEN, NEAR_DARK, BLUE, ORANGE, "#7A6FF0"]
    bars = ax.bar(range(len(values)), [v or 0 for v in values], color=colors)
    ax.set_yscale("log")
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels(labels)
    style_ax(ax, "What the market pays per $1 of annualised fees",
             ylabel="Market cap / annualised fees (x, log scale)")
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, (v or 0) * 1.15,
                f"{v:,.0f}x" if v else "n/a", ha="center", fontsize=10,
                fontweight="bold")
    ax.text(0.02, 0.96,
            "NEAR retained uses the measured 30D capture rate;\npeers use "
            "DefiLlama 30d chain fees annualised.\nSources: CoinGecko + DefiLlama.",
            transform=ax.transAxes, fontsize=8, color=GREY, va="top")
    save(fig, "chart04_valuation_multiples.png")


def chart05():
    d = load("chart_05_data.json")
    labels = [f"{int(s['capture'] * 100)}% capture" for s in d["scenarios"]]
    vals = [s["bought_per_year_near"] / 1e6 for s in d["scenarios"]]
    labels.append(f"Measured {d['measured']['capture'] * 100:.0f}% capture")
    vals.append(d["measured"]["bought_per_year_near"] / 1e6)
    issued = d["issued_per_year_near"] / 1e6
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = [GREY, BLUE, NEAR_GREEN, NEAR_DARK]
    bars = ax.barh(labels, vals, color=colors)
    ax.axvline(issued, color="#C0392B", lw=2, ls="--",
               label=f"Issued/yr: {issued:,.1f}M NEAR")
    for b, v in zip(bars, vals):
        ax.text(v + issued * 0.02, b.get_y() + b.get_height() / 2,
                f"{v:,.1f}M NEAR/yr", va="center", fontsize=10)
    ax.set_xlim(0, max(issued * 1.25, max(vals) * 1.3))
    style_ax(ax, "Buybacks vs issuance — still inflationary, with a visible line",
             xlabel="NEAR / year (millions)")
    ax.legend(frameon=False, loc="upper right")
    ax.text(0.01, 0.02,
            f"Break-even retained revenue: "
            f"{d['break_even_retained_revenue_usd'] / 1e6:,.1f}M USD/yr at the "
            f"current price. Sources: DefiLlama + RPC + NEARBlocks.",
            transform=ax.transAxes, fontsize=8, color=GREY)
    save(fig, "chart05_buyback_vs_issuance.png")


def chart06():
    d = load("chart_06_data.json")
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = ["Staking APY\n(last epoch)", "Max inflation", "Real yield\nto stakers"]
    vals = [d["apy_pct"], d["inflation_pct"], d["real_yield_pct"]]
    bars = ax.bar(labels, vals, color=[NEAR_GREEN, ORANGE, BLUE])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.15, f"{v:.2f}%",
                ha="center", fontsize=11, fontweight="bold")
    ax.set_ylim(0, max(vals) * 1.3)
    style_ax(ax, "Staking economics — positive real yield, but dilution persists",
             ylabel="% per year")
    ax.text(0.01, 0.97,
            f"Total staked: {d['total_staked_near']:,.0f} NEAR "
            f"({d['total_staked_share_pct']}% of supply) · "
            f"Validators: {d['current_validators']} · "
            f"Top-10 stake share: {d['top_10_share_pct']}%",
            transform=ax.transAxes, fontsize=9, va="top")
    save(fig, "chart06_staking_economics.png")


def chart07():
    d = load("chart_07_data.json")
    vals = np.array([[v if v is not None else np.nan for v in row]
                     for row in d["values_per_token_usd"]], dtype=float)
    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(vals, cmap="Greens", aspect="auto")
    ax.set_xticks(range(len(d["growth_scenarios"])))
    ax.set_xticklabels([f"g = {int(g * 100)}%" for g in d["growth_scenarios"]])
    ax.set_yticks(range(len(d["capture_scenarios"])))
    ax.set_yticklabels([f"capture {int(c * 100)}%" for c in d["capture_scenarios"]])
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = vals[i, j]
            ax.text(j, i, f"${v:.2f}" if not np.isnan(v) else "n/a (g≥r)",
                    ha="center", va="center", fontsize=12, fontweight="bold",
                    color="white" if not np.isnan(v) and v > np.nanmax(vals) * 0.6 else "black")
    style_ax(ax, f"Implied NEAR value/token — fee-capture DCF "
                 f"(r = {int(d['discount_rate'] * 100)}%)", ylabel="")
    fig.colorbar(im, ax=ax, label="USD / token")
    ax.text(0.01, -0.22,
            f"Current price: {d['current_price_usd']:.2f} USD — above every cell: "
            f"the market pays for growth/capture beyond this grid. "
            f"Base case: {d['base_case_value_per_token_usd']:.2f} USD/token.",
            transform=ax.transAxes, fontsize=8, color=GREY)
    save(fig, "chart07_sensitivity_heatmap.png")


def chart08():
    d = load("chart_08_data.json")
    if not d.get("available"):
        print("chart08 SKIPPED: no NEARBlocks /v1/charts series")
        return
    dates = np.array([np.datetime64(x) for x in d["dates"]])
    txns = np.array(d["daily_txns"], dtype=float)
    ac_dates = np.array([np.datetime64(x) for x in d["active_dates"]])
    accts = np.array(d["daily_active_accounts"], dtype=float)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax1.plot(dates, txns, color=NEAR_GREEN, lw=0.8)
    ax1.set_yscale("log")
    pk = d["txns_peak"]
    pk_date = np.datetime64(pk["date"])
    ax1.scatter([pk_date], [pk["value"]], color="#C0392B", s=45, zorder=5)
    ax1.annotate(f"Peak {pk['value']:,.0f}/day\n{pk['date']}",
                 xy=(pk_date, pk["value"]), xytext=(8, 8),
                 textcoords="offset points", fontsize=9, color="#C0392B",
                 fontweight="bold")
    style_ax(ax1, "Daily transactions on NEAR, 2020 → today",
             ylabel="Txns / day (log scale)")
    ax2.plot(ac_dates, accts, color=BLUE, lw=0.8)
    ax2.set_yscale("log")
    pk2 = d["accounts_peak"]
    pk2_date = np.datetime64(pk2["date"])
    ax2.scatter([pk2_date], [pk2["value"]], color="#C0392B", s=45, zorder=5)
    ax2.annotate(f"Peak {pk2['value']:,.0f}/day\n{pk2['date']}",
                 xy=(pk2_date, pk2["value"]), xytext=(8, 8),
                 textcoords="offset points", fontsize=9, color="#C0392B",
                 fontweight="bold")
    style_ax(ax2, "Daily active accounts on NEAR, 2020 → today",
             ylabel="Active accounts / day (log scale)")
    fig.text(0.01, 0.01,
             f"Latest day ({d['dates'][-1]}): {d['txns_current']:,.0f} txns "
             f"({d['txns_pct_below_peak']}% below peak; 30d avg "
             f"{d['txns_30d_avg']:,.0f}) and {d['accounts_current']:,.0f} active "
             f"accounts ({d['accounts_pct_below_peak']}% below peak; 30d avg "
             f"{d['accounts_30d_avg']:,.0f}). Source: NEARBlocks /v1/charts "
             f"({len(dates)} daily points).",
             fontsize=8, color=GREY)
    save(fig, "chart08_daily_activity.png")


def chart09():
    d = load("chart_09_data.json")
    if not d.get("available"):
        print(f"chart09 SKIPPED: {d.get('reason')}")
        return
    dates = np.array([np.datetime64(x) for x in d["dates"]])
    vol = np.array(d["daily_volume_usd"], dtype=float)
    vma = np.array(d["volume_ma30_usd"], dtype=float)
    fee_dates = np.array([np.datetime64(x) for x in d["fee_dates"]])
    fees = np.array(d["daily_fees_usd"], dtype=float)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax1.plot(dates, vol, color=GREY, lw=0.6, alpha=0.6, label="Daily volume")
    ax1.plot(dates, vma, color=NEAR_GREEN, lw=2, label="30-day moving average")
    ax1.set_yscale("log")
    style_ax(ax1, "NEAR Intents daily volume — the growth x-axis",
             ylabel="USD / day (log scale)")
    ax1.legend(frameon=False, loc="upper left")
    ax2.plot(fee_dates, fees, color=GREY, lw=0.6, alpha=0.6, label="Daily fees")
    ax2.set_yscale("log")
    style_ax(ax2, "NEAR Intents daily fees — the revenue (same dates, fees series)",
             ylabel="USD / day (log scale)")
    fig.text(0.01, 0.01,
             f"Volume 30d: ${d['volume_30d_usd']:,.0f} "
             f"({d['volume_30d_vs_prior_30d_pct']:+.1f}% vs prior 30d); fees 30d: "
             f"${d['fees_30d_usd']:,.0f}; implied gross fee rate "
             f"{d['implied_gross_fee_rate_30d_bps']:.2f} bps. Peak daily volume "
             f"${d['peak_daily_volume']['volume_usd']:,.0f} on "
             f"{d['peak_daily_volume']['date']}. Sources: DefiLlama dexs "
             f"(volume) + fees (fees).",
             fontsize=8, color=GREY)
    save(fig, "chart09_intents_volume_and_fees.png")


def chart10():
    d = load("chart_10_data.json")
    if not d.get("available"):
        print(f"chart10 SKIPPED: {d.get('reason')}")
        return
    import numpy as _np
    users = _np.array(d["monthly_users_mean"], dtype=float)
    price = _np.array(d["monthly_price_month_end"], dtype=float)
    cum = _np.array(d["monthly_cum_txns_month_end"], dtype=float)
    f1 = d["fit_price_vs_users"]
    f2 = d["fit_price_vs_cum_txns"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    # Panel 1: price vs users, log-log, with the OLS fit. Strict Metcalfe
    # (value ∝ users²) would be a slope-2 line; the fitted slope is ~0.02.
    ax1.scatter(users, price, color=BLUE, s=28, alpha=0.75, zorder=3,
                label="Monthly: mean users vs month-end price")
    xs = _np.linspace(users.min(), users.max(), 50)
    ax1.plot(xs, _np.exp(f1["intercept"] + f1["slope"] * _np.log(xs)),
             color="#C0392B", lw=2,
             label=f"OLS fit: slope {d['slope_monthly']:.2f}, "
                   f"R² {d['r_squared_monthly']:.3f}")
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    style_ax(ax1, "Price vs users — no Metcalfe law",
             xlabel="Monthly mean active accounts / day (log scale)",
             ylabel="NEAR price, month-end USD (log scale)")
    ax1.legend(frameon=False, loc="upper left", fontsize=9)
    ax1.text(0.02, 0.02,
             f"n={d['n_months']} months, {d['window']}. Pearson r "
             f"{d['pearson_r_monthly']:.2f}. Strict Metcalfe needs slope ≈ 2.0.",
             transform=ax1.transAxes, fontsize=8, color=GREY)
    # Panel 2: price vs cumulative txns (PARTIAL — trend-dominated stock).
    ax2.scatter(cum, price, color=NEAR_GREEN, s=28, alpha=0.75, zorder=3,
                label="Monthly: cumulative txns vs month-end price")
    xs2 = _np.linspace(cum.min(), cum.max(), 50)
    ax2.plot(xs2, _np.exp(f2["intercept"] + f2["slope"] * _np.log(xs2)),
             color="#C0392B", lw=2,
             label=f"OLS fit: slope {d['slope_cum_txns']:.2f}, "
                   f"R² {d['r_squared_cum_txns']:.3f}")
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    style_ax(ax2, "Price vs cumulative txns — partial check",
             xlabel="Cumulative transactions to date (log scale)",
             ylabel="NEAR price, month-end USD (log scale)")
    ax2.legend(frameon=False, loc="upper left", fontsize=9)
    ax2.text(0.02, 0.02,
             "PARTIAL: cumulative txns only rises, so this test is "
             "trend-dominated by construction.",
             transform=ax2.transAxes, fontsize=8, color=GREY)
    fig.text(0.01, -0.01,
             f"Daily regression agrees (slope {d['slope_daily']:.2f}, "
             f"R² {d['r_squared_daily']:.3f}, n=2,218 days). Market-cap version: "
             f"slope {d['slope_mcap_monthly']:.2f}, R² "
             f"{d['r_squared_mcap_monthly']:.3f}. A fellow entry (NEAR Demand "
             f"Ledger) reports slope {d['rival_slope']:.2f}, R² "
             f"{d['rival_r_squared']:.2f} on 73 months — same direction "
             f"(disconnect), weaker on this series. Caveat: from Jan 2024 the "
             f"monthly slope is {d['slope_subwindow_2024']:.2f} (r "
             f"{d['r_subwindow_2024']:.2f}) — the joint fall from the Apr 2024 "
             f"peak, not a stable law. Source: NEARBlocks /v1/charts.",
             fontsize=8, color=GREY)
    save(fig, "chart10_metcalfe_price_vs_users.png")


def main():
    chart01()
    chart02()
    chart03()
    chart04()
    chart05()
    chart06()
    chart07()
    chart08()
    chart09()
    chart10()
    print(f"10 charts -> {OUT}")


if __name__ == "__main__":
    main()
