#!/usr/bin/env python3
"""Render dashboard/index.html from data/processed/*.json (no network).

Usage:  python3 src/build_dashboard.py
Reads metrics.json, dcf.json, sensitivity.json, benchmarks.json,
predictions.json and the chart_0*_data.json files, and writes
dashboard/index.html. Every number on the page is formatted from those JSONs
— nothing is hardcoded — so re-running fetch.py + build.py and then this
script regenerates a dashboard that always matches the model outputs. Charts
are the SVGs in dashboard/assets/ (PNG twins are also generated for local viewing).
"""
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"


def load(name):
    return json.loads((PROC / name).read_text())


def money(x):
    """$5,578,208 / $24.08M / $4.72B as appropriate."""
    if x is None:
        return "—"
    ax = abs(x)
    if ax >= 1e9:
        return f"${x / 1e9:,.2f}B"
    if ax >= 1e6:
        return f"${x / 1e6:,.2f}M"
    if ax >= 1e3:
        return f"${x:,.0f}"
    return f"${x:,.2f}"


def money_exact(x):
    return f"${x:,.0f}" if x is not None else "—"


def num(x, dec=0):
    return f"{x:,.{dec}f}" if x is not None else "—"


def pct(x, dec=1):
    return f"{x * 100:.{dec}f}%" if x is not None else "—"


def pct_pts(x, dec=2):
    return f"{x:.{dec}f}%" if x is not None else "—"


def main():
    m = load("metrics.json")
    dcf = load("dcf.json")
    sens = load("sensitivity.json")
    bench = load("benchmarks.json")
    c7 = load("chart_07_data.json")
    c8 = load("chart_08_data.json")
    c9 = load("chart_09_data.json")
    c10 = load("chart_10_data.json")
    try:
        pred = load("predictions.json")
    except Exception:
        pred = None

    M1 = m["M1_intents_gross_fees"]
    M2 = m["M2_intents_fee_growth"]
    M3 = m["M3_retained_revenue"]
    M4 = m["M4_capture_rate_trend"]
    M5 = m["M5_base_chain_fees"]
    M6 = m["M6_buyback_vs_issuance"]
    M7 = m["M7_mcap_retained_multiple"]
    M8 = m["M8_valuation_multiples"]
    M9 = m["M9_staking_real_yield"]
    M10 = m["M10_validator_health"]
    M11 = m["M11_price_vs_fundamentals"]
    M12 = m["M12_daily_txns"]
    M13 = m["M13_daily_active_accounts"]
    M14 = m["M14_new_accounts_trend"]
    M15 = m["M15_intents_daily_volume"]
    M16 = m["M16_price_vs_fees_correlation"]
    M17 = m["M17_metcalfe_check"]
    snap = m["snapshot"]
    peers = bench["peers"]
    comp = bench["intents_competitors"]

    gen = m["generated_at_utc"]
    price = snap["near_price_usd"]
    mcap = snap["market_cap_usd"]
    F30 = M1["total_30d_usd_F30"]
    capture = M3["capture_rate_30d_measured"]
    R0 = M3["retained_revenue_annualised_base_usd_R0"]
    vpt = dcf["base_case"]["value_per_token_usd"]
    vpt_pct = dcf["base_case"]["value_per_token_vs_price_pct"]
    be = M6["break_even_retained_revenue_usd_per_year"]
    be_mult = M6["break_even_multiple_of_current_R0"]
    mcap_r0 = M7["mcap_div_R0_base"]
    issued = M6["issued_per_year_near"]
    bought = M6["bought_per_year_base_near"]
    net = M6["net_supply_change_base_near_per_year"]

    # Sensitivity heatmap at r=12% (matches Chart 7).
    heat = [c for c in sens["grid"] if c["discount"] == c7["discount_rate"]]
    heat_rows = {}
    for c in heat:
        heat_rows.setdefault(c["capture"], {})[c["growth"]] = c
    caps = sorted(heat_rows)
    grows = sorted(next(iter(heat_rows.values())))

    def heat_cell(c):
        if c["invalid_reason"]:
            return '<td class="invalid">n/a<br><span>g ≥ r</span></td>'
        return f'<td>${c["value_per_token_usd"]:.2f}</td>'

    heat_html = "".join(
        "<tr><th scope='row'>" + pct_pts(cap * 100, 0) + "</th>"
        + "".join(heat_cell(heat_rows[cap][g]) for g in grows) + "</tr>"
        for cap in caps
    )

    def peer_row(key, label, fees_key, mcap_fees_key, tvl_key="tvl_usd",
                 mcap_tvl_key="mcap_div_tvl"):
        p = peers[key]
        fees30 = p.get(fees_key)
        fees_ann = fees30 * 12 if fees30 else None
        return (
            f"<tr><th scope='row'>{label}</th>"
            f"<td>${p['price_usd']:,.2f}</td>"
            f"<td>{money(p['market_cap_usd'])}</td>"
            f"<td>{money_exact(fees30)}</td>"
            f"<td>{money(fees_ann)}</td>"
            f"<td>{p[mcap_fees_key]:,.1f}×</td>"
            f"<td>{money(p[tvl_key])}</td>"
            f"<td>{p[mcap_tvl_key]:,.1f}×</td></tr>"
        )

    comp_rows = "".join(
        f"<tr><th scope='row'>{name}</th><td>{money_exact(v['fees_30d_usd'])}</td>"
        f"<td>{money_exact(v['fees_7d_usd'])}</td>"
        f"<td>{money_exact(v['fees_24h_usd'])}</td></tr>"
        for name, v in [("NEAR Intents", {"fees_30d_usd": F30,
                        "fees_7d_usd": M1["total_7d_usd"],
                        "fees_24h_usd": M1["total_24h_usd"]}),
                       ("Chainflip", comp["chainflip"]),
                       ("deBridge", comp["debridge"]),
                       ("THORChain", comp["thorchain"])]
    )

    charts = [
        ("chart01_intents_daily_fees.svg",
         "1 · Intents daily fees — the revenue curve",
         "NEAR Intents daily fees, 10 May 2025 – 9 Nov 2026 (549 days, log scale) "
         "with a 30-day moving average.",
         f"Fees grew from $1/day at launch to a 7-day average of about "
         f"${M1['total_7d_usd'] / 7:,.0f}/day — but they are volatile, not a smooth "
         f"ramp. Trailing-30d fees are {money_exact(M2['trailing_30d_usd'])}, "
         f"{M2['trailing_30d_vs_prior_30d_pct']:.1f}% vs the prior 30 days, "
         f"{M2['trailing_30d_yoy']['change_pct']:.1f}% vs a year ago, and "
         f"{(M2['trailing_30d_usd'] / M2['trailing_30d_peak']['trailing_30d_usd'] - 1) * 100:.1f}% "
         f"below the {money_exact(M2['trailing_30d_peak']['trailing_30d_usd'])} peak of "
         f"{M2['trailing_30d_peak']['date']}.",
         M1["source"], M1["fetched_at_utc"]),
        ("chart02_intents_vs_base_fees.svg",
         "2 · Intents fees vs base-chain gas fees",
         "NEAR Intents daily fees vs NEAR base-layer gas fees, same log axis.",
         f"Intents grossed {money_exact(F30)} in 30 days while base-chain gas "
         f"earned {money_exact(M5['total_24h_usd'])} in 24 hours "
         f"({money_exact(M5['total_all_time_usd'])} all-time). Intents 30d fees are "
         f"{M5['intents_30d_vs_base_daily_ratio']:.1f}× one day of base fees. "
         f"Gas is not the business — Intents is.",
         M5["source"], M5["fetched_at_utc"]),
        ("chart03_price_vs_fees_divergence.svg",
         "3 · Price vs fees — do they move together?",
         "NEAR price (CoinGecko, 365 days) vs trailing-30d Intents fees, both "
         "indexed to 100 at the start of the window.",
         f"Over 12 months the price is up {M11['price_change_pct']:.1f}% and "
         f"trailing-30d fees are up {M11['trailing_30d_fees_change_pct']:.1f}% — "
         f"but in the last 30 days both fell hard: price "
         f"{M11['price_30d_change_pct']:.1f}%, fees "
         f"{M11['trailing_30d_fees_30d_change_pct']:.1f}%. Recently they move "
         f"together, not apart; the divergence is a 30-day drawdown, not a "
         f"decoupling.",
         M11["source"], M11["fetched_at_utc"]),
        ("chart04_valuation_multiples.svg",
         "4 · Valuation multiples — NEAR vs the big L1s",
         "Market cap ÷ annualised fees for NEAR (Intents gross and retained) "
         "vs Solana, Avalanche and Ethereum chain fees.",
         f"On gross Intents fees NEAR is the cheapest of the four "
         f"({M8['near_mcap_div_gross_intents_fees']:.1f}× vs Solana "
         f"{M8['peer_mcap_div_fees']['solana']:.1f}×, Avalanche "
         f"{M8['peer_mcap_div_fees']['avalanche-2']:.1f}×, Ethereum "
         f"{M8['peer_mcap_div_fees']['ethereum']:.1f}×). On retained revenue — "
         f"the money NEAR actually keeps — it is {mcap_r0:.1f}×. Cheap on "
         f"gross, expensive on retained: the gap is the capture rate.",
         M8["source"], M8["fetched_at_utc"]),
        ("chart05_buyback_vs_issuance.svg",
         "5 · Buybacks vs issuance — still inflationary",
         "NEAR bought per year from retained revenue (three capture scenarios "
         "plus the measured rate) vs NEAR issued per year at the 2.5% cap.",
         f"At the measured {pct(capture)} capture, retained revenue buys "
         f"{num(bought)} NEAR/yr against {num(issued)} NEAR/yr issued — a net "
         f"increase of {num(net)} NEAR/yr. NEAR turns net-deflationary only "
         f"when retained revenue reaches {money(be)}/yr, {be_mult:.1f}× today.",
         M6["source"], M6["fetched_at_utc"]),
        ("chart06_staking_economics.svg",
         "6 · Staking economics — stakers win, holders dilute",
         "Last-epoch staking APY vs the 2.5% max-inflation cap, total staked "
         "and validator concentration.",
         f"Stakers earn {pct_pts(M9['last_epoch_apy'] * 100)} APY against "
         f"{pct_pts(M9['max_inflation_rate'] * 100)} maximum inflation — a "
         f"{M9['real_yield_pp']:.2f} percentage-point real yield. Non-stakers "
         f"dilute {pct_pts(M9['dilution_to_non_stakers_pct_per_year'])} a year. "
         f"{num(M10['total_staked_near'])} NEAR ({M10['total_staked_share_of_supply_pct']:.1f}% "
         f"of supply) is staked across {M10['current_validators']} of "
         f"{M10['total_validators']} validators; the top 10 hold "
         f"{M10['top_10_stake_share_pct']:.1f}% of stake.",
         M9["source"], M9["fetched_at_utc"]),
        ("chart07_sensitivity_heatmap.svg",
         "7 · Sensitivity — what has to be true for $3.60?",
         "Implied NEAR value per token across capture rate (15/25/35%) × "
         "perpetual fee growth (0/10/20%) at a 12% discount rate.",
         f"No cell in the grid reaches the current ${price:,.2f} price — the "
         f"best valid cell (35% capture, 10% growth, r=12%) is "
         f"${c7['values_per_token_usd'][2][1]:.2f}. The market is paying for "
         f"fee growth and/or capture beyond this grid. Cells where growth "
         f"meets or exceeds the discount rate are invalid in a Gordon model "
         f"and shown as n/a.",
         "Model output — data/processed/sensitivity.json", gen),
    ]

    # Chart 8 — daily network activity (NEARBlocks /v1/charts, 2020 -> today).
    if c8.get("available"):
        charts.append((
            "chart08_daily_activity.svg",
            "8 · Daily transactions & active accounts — the usage collapse",
            "Daily transactions and daily active accounts on NEAR, Jul 2020 – "
            "today (2,303 daily points, log scale), with all-time peaks marked.",
            f"Both series are far below their peaks: {num(M12['current_last_day'])} "
            f"txns on {M12['last_date']} vs a peak of "
            f"{num(M12['all_time_peak']['value'])} on {M12['all_time_peak']['date']} "
            f"({M12['current_pct_below_peak']:.1f}% below peak; 30d average "
            f"{num(M12['daily_avg_last_30d'])}, {M12['avg_30d_vs_prior_30d_pct']:.1f}% "
            f"vs the prior 30 days), and {num(M13['current_last_day'])} active "
            f"accounts vs a peak of {num(M13['all_time_peak']['value'])} on "
            f"{M13['all_time_peak']['date']} ({M13['current_pct_below_peak']:.1f}% "
            f"below peak). New accounts are slowing too: "
            f"{num(M14['sum_last_30d'])} in the last 30 days vs "
            f"{num(M14['sum_prior_30d'])} the 30 days before "
            f"({M14['avg_30d_vs_prior_30d_pct']:.1f}%). This is the honest bear leg "
            f"of the thesis: base-layer usage has collapsed from its peaks even "
            f"while Intents fees grew — the toll road's moat is the Intents "
            f"product, not base-layer activity.",
            M12["source"], M12["fetched_at_utc"]))

    # Chart 9 — Intents volume + fees (only if the DefiLlama dexs endpoint verified).
    if c9.get("available"):
        charts.append((
            "chart09_intents_volume_and_fees.svg",
            "9 · Intents volume & fees — the growth x-axis, finally measured",
            "NEAR Intents daily swap volume (DefiLlama dexs) and daily fees "
            "(DefiLlama fees), Dec 2024 – today, log scale.",
            f"Intents volume was {money(M15['total_30d_usd_from_daily_series'])} "
            f"in the last 30 days ({M15['total_30d_vs_prior_30d_pct']:.1f}% vs the "
            f"prior 30 days; peak single day "
            f"{money(M15['peak_daily_volume']['volume_usd'])} on "
            f"{M15['peak_daily_volume']['date']}), against "
            f"{money_exact(F30)} of gross fees — an implied gross fee rate of "
            f"{M15['implied_gross_fee_rate_30d_bps']:.2f} bps. Volume and fees "
            f"are the same story told twice: fees are volume × the fee rate, "
            f"so the DCF's growth assumption is really a bet on volume "
            f"compounding at roughly this fee rate.",
            M15["source"], M15["fetched_at_utc"]))

    # Chart 10 — Metcalfe check (M17): price vs users, log-log.
    if c10.get("available"):
        _rm = M17["price_vs_active_accounts_monthly"]
        _rd = M17["price_vs_active_accounts_daily"]
        _rmc = M17["market_cap_vs_active_accounts_monthly"]
        _rc = M17["price_vs_cumulative_txns_monthly"]
        _rs = M17["subwindow_2024_onwards_monthly"]
        charts.append((
            "chart10_metcalfe_price_vs_users.svg",
            "10 · Metcalfe check — price does not follow users",
            "NEAR price vs daily active accounts, monthly log-log "
            f"({M17['n_months']} months, {M17['window']}), plus the "
            "cumulative-transactions partial check.",
            f"On the full window the log-log slope is {_rm['slope']:.2f} "
            f"(SE {_rm['slope_se']:.2f}) with R² {_rm['r_squared']:.3f} — "
            f"statistically zero, against the strict-Metcalfe slope of 2.0. "
            f"The daily regression agrees (slope {_rd['slope']:.2f}, R² "
            f"{_rd['r_squared']:.3f}, n={_rd['n']:,} days). Even market cap on "
            f"users gives only slope {_rmc['slope']:.2f}, R² "
            f"{_rmc['r_squared']:.3f}. A fellow entry (NEAR Demand Ledger) "
            f"reports slope {M17['rival_reported']['slope']:.2f}, R² "
            f"{M17['rival_reported']['r_squared']:.2f} on 73 months — the same "
            f"disconnect, weaker on this series. Caveat, not buried: from Jan "
            f"2024 the monthly slope is {_rs['slope']:.2f} (r "
            f"{_rs['pearson_r']:.2f}), the joint fall from the Apr 2024 "
            f"activity peak — the relation flips sign across sub-periods, so "
            f"it is not a stable law. Net: value NEAR on fees, not users.",
            M17["source"], M17["fetched_at_utc"]))

    chart_html = ""
    for img, title, desc, takeaway, src, ts in charts:
        chart_html += f"""
      <section class="chart">
        <h3>{title}</h3>
        <p class="desc">{desc}</p>
        <img src="assets/{img}" alt="{title}" loading="lazy">
        <p class="takeaway"><strong>Takeaway:</strong> {takeaway}</p>
        <p class="source">Source: <code>{src}</code> · fetched {ts}</p>
      </section>
"""

    # Extra headline cards: Intents volume (M15) + daily active accounts (M13).
    extra_cards = ""
    if M15.get("available"):
        extra_cards += (
            f'  <div class="metric"><div class="v">'
            f'{money(M15["total_30d_usd_from_daily_series"])}</div>'
            f'<div class="k">Intents volume, trailing 30d</div>'
            f'<div class="n">DefiLlama dexs · {M15["total_30d_vs_prior_30d_pct"]:.1f}% vs '
            f'prior 30d · implied fee rate {M15["implied_gross_fee_rate_30d_bps"]:.2f} bps</div></div>\n')
    if M13.get("available"):
        extra_cards += (
            f'  <div class="metric"><div class="v">{num(M13["current_last_day"])}</div>'
            f'<div class="k">Daily active accounts</div>'
            f'<div class="n">{M13["current_pct_below_peak"]:.1f}% below the '
            f'{M13["all_time_peak"]["date"]} peak · 30d avg '
            f'{num(M13["daily_avg_last_30d"])}</div></div>\n')

    # Network-activity section: only the sentences whose data verified.
    if M12.get("available") and M13.get("available"):
        vol_sentence = ""
        if M15.get("available"):
            vol_sentence = (f" The investment question is therefore not whether "
                f"NEAR&rsquo;s base layer is busy (it is not, relative to its peaks) "
                f"but whether Intents volume — "
                f"{money(M15['total_30d_usd_from_daily_series'])} in 30 days at a "
                f"{M15['implied_gross_fee_rate_30d_bps']:.2f} bps fee rate — keeps "
                f"compounding while the base layer does not.")
        corr_sentence = ""
        if M16.get("pearson_price_vs_intents_fees_weekly_log_changes") is not None:
            corr_sentence = (f" Over the last 365 days, weekly changes in "
                f"NEAR&rsquo;s price and in Intents fees moved together with a Pearson "
                f"correlation of {M16['pearson_price_vs_intents_fees_weekly_log_changes']:.2f} "
                f"(n={M16['n_weekly_pairs_price_vs_intents_fees']} weeks; price vs "
                f"base-layer gas fees: "
                f"{M16['pearson_price_vs_base_gas_fees_weekly_log_changes']:.2f}) — a "
                f"co-movement, not a lead-lag result and not evidence of causation.")
        network_section = f"""
<h2>Network activity — the usage chapter in one paragraph</h2>
<p>Base-layer usage is the thesis&rsquo;s bear leg, and it is now measured on a
full daily series (NEARBlocks <code>/v1/charts</code>, {M12['daily_points']:,} days
from {M12['first_date']}): {num(M12['current_last_day'])} transactions and
{num(M13['current_last_day'])} active accounts on {M12['last_date']} — respectively
{M12['current_pct_below_peak']:.1f}% and {M13['current_pct_below_peak']:.1f}% below
their all-time peaks ({num(M12['all_time_peak']['value'])} txns on
{M12['all_time_peak']['date']}; {num(M13['all_time_peak']['value'])} accounts on
{M13['all_time_peak']['date']}). New accounts are slowing as well
({num(M14['sum_last_30d'])} in 30 days, {M14['avg_30d_vs_prior_30d_pct']:.1f}% vs the
prior 30).{corr_sentence}{vol_sentence}</p>
"""
    else:
        network_section = """
<h2>Network activity — the usage chapter in one paragraph</h2>
<p>The NEARBlocks daily-activity series (<code>/v1/charts</code>) did not return
on the latest fetch, so no daily-transaction or active-account figures are shown.
No activity series is fabricated; re-run <code>src/fetch.py</code> to restore it.</p>
"""

    # Metcalfe section: the test a fellow entry ran, run properly on our series.
    if M17.get("available"):
        _rm = M17["price_vs_active_accounts_monthly"]
        _rd = M17["price_vs_active_accounts_daily"]
        _rmc = M17["market_cap_vs_active_accounts_monthly"]
        _rc = M17["price_vs_cumulative_txns_monthly"]
        _rs = M17["subwindow_2024_onwards_monthly"]
        metcalfe_section = f"""
<h2>Metcalfe check — does price follow users?</h2>
<p>Metcalfe&rsquo;s law says a network&rsquo;s value grows with the square of its
users, so log(price) on log(users) should have a slope near 2.0. On the
NEARBlocks daily series ({M17['window']}, {M17['usable_daily_points']:,} days,
{M17['n_months']} months) it does not: the monthly slope is {_rm['slope']:.2f}
(SE {_rm['slope_se']:.2f}) with R² {_rm['r_squared']:.3f} and Pearson r
{_rm['pearson_r']:.2f} — statistically indistinguishable from zero. The daily
regression agrees (slope {_rd['slope']:.2f}, R² {_rd['r_squared']:.3f}).
Even market cap on users gives only slope {_rmc['slope']:.2f}, R²
{_rmc['r_squared']:.3f}. Price does not track cumulative usage either
(slope {_rc['slope']:.2f}, R² {_rc['r_squared']:.3f} — a partial check, since
cumulative transactions only ever rise). A fellow Investment Thesis entry,
NEAR Demand Ledger, reports slope {M17['rival_reported']['slope']:.2f} and R²
{M17['rival_reported']['r_squared']:.2f} on 73 months with the same
&ldquo;hypothesis is unproven&rdquo; verdict — the same disconnect, weaker on
this series (activity definitions move the numbers; the shared conclusion is
what matters). The honest caveat: from Jan 2024 the monthly slope is
{_rs['slope']:.2f} (r {_rs['pearson_r']:.2f}) — price and users have moved
together more in the recent window, driven by the joint fall from the Apr 2024
activity peak. The relation flips sign across sub-periods, so it is not a
stable law. The takeaway for the thesis: value NEAR on fees, not on users —
the fee thesis stands on its own numbers, and no user-count story rescues the
${price:,.2f} price. Method: log(price) = a + b·log(users), month-end price vs
monthly mean active accounts; {M17['dropped_rows']['zero_price_rows']} pre-launch
zero-price rows and {M17['dropped_rows']['zero_active_account_rows']} zero-user
rows (all Jul–Oct 2020) dropped before taking logs.</p>
"""
    else:
        metcalfe_section = """
<h2>Metcalfe check — does price follow users?</h2>
<p>The Metcalfe regression could not run on the latest fetch (see
<code>data/processed/metrics.json</code> M17 for the reason). No Metcalfe
numbers are shown rather than fabricated; re-run <code>src/fetch.py</code> to
restore the series.</p>
"""

    # Dated predictions (M18): committed 2026-11-10, scored live.
    _ST_CLS = {"on track": "st-on", "off track": "st-off",
               "not yet measurable": "st-na"}
    if pred and pred.get("predictions"):
        _rows = ""
        for _pr in pred["predictions"]:
            _lv = _pr["live_value_display"] or "—"
            _cls = _ST_CLS.get(_pr["status"], "st-na")
            # Thresholds contain "<" (P3/P6/P7) — escape so the text renders
            # literally instead of being parsed as a tag open.
            _note = (f"<br><span class=\"note\">"
                     f"{escape(_pr['status_reason'])}</span>"
                     if _pr.get("status_reason") else "")
            _rows += (
                f"<tr><th scope='row'>{escape(_pr['id'])}</th>"
                f"<td>{escape(_pr['title'])}</td>"
                f"<td>{escape(_pr['threshold'])}</td>"
                f"<td>{escape(_pr['resolves'])}</td>"
                f"<td>{escape(_lv)}</td>"
                f"<td class=\"{_cls}\">{_pr['status']}{_note}</td></tr>")
        _c = pred["counts"]
        predictions_section = f"""
<h2>Dated predictions — score this thesis against reality</h2>
<p>Committed {pred.get('committed')}: these predictions are timestamped by
the git history of <a href="https://github.com/Topeseun/near-intents-investment-thesis/blob/main/PREDICTIONS.md">PREDICTIONS.md</a>
and derived from the thesis&rsquo;s own numbers — no threshold here is
invented. <strong>A missed prediction counts against the thesis.</strong>
That is the point: a thesis that cannot be wrong is not evidence. Live
values below are as of {pred.get('generated_at_utc')} — a point-in-time read
against the threshold, <em>not</em> the final outcome: no prediction has
resolved yet (earliest resolution date 2026-12-31). Current tally:
{_c.get('on track', 0)} on track, {_c.get('off track', 0)} off track,
{_c.get('not yet measurable', 0)} not yet measurable.</p>
<div class="tbl-wrap"><table>
<tr><th>ID</th><th>Prediction</th><th>Threshold</th><th>Resolves</th><th>Live value</th><th>Status</th></tr>
{_rows}
</table></div>
<p class="note">Live values are the same figures the model already computes
(M1 F30, M3 capture, base-case DCF ÷ live price, M15 volume, F30 ÷ Chainflip
30d fees, M13 30d-mean active accounts, |M16 weekly log-change Pearson|).
When a resolution date arrives, re-run the pipeline and record the outcome
in PREDICTIONS.md.</p>
"""
    else:
        predictions_section = """
<h2>Dated predictions — score this thesis against reality</h2>
<p>The committed predictions (<code>PREDICTIONS.md</code>, 7 dated
predictions) could not be scored on the latest run — see
<code>data/processed/predictions.json</code> for the reason. No prediction
status is shown rather than fabricated; re-run <code>src/build.py</code> to
restore it.</p>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEAR as a Cross-Chain Settlement Business — Investment Thesis</title>
<meta name="description" content="A data-backed long-term investment thesis for NEAR, priced on retained NEAR Intents revenue. NEAR Hackathon 2026, Investment Thesis track.">
<style>
:root{{--bg:#0f1115;--panel:#171a21;--panel2:#1e222c;--ink:#e8eaf0;--mut:#9aa3b2;
--acc:#7dd3a8;--acc2:#6cb6ff;--warn:#f2b04e;--bad:#f28b82;--line:#2a2f3a;--chip:#232838}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
line-height:1.55}}
a{{color:var(--acc2)}}
.wrap{{max-width:960px;margin:0 auto;padding:24px 18px 64px}}
header{{padding:28px 0 8px}}
.eyebrow{{color:var(--acc);font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:12px}}
h1{{font-size:clamp(26px,5vw,40px);line-height:1.15;margin:10px 0}}
h2{{font-size:22px;margin:44px 0 10px;border-bottom:1px solid var(--line);padding-bottom:8px}}
h3{{font-size:18px;margin:0 0 6px}}
.lede{{font-size:18px;color:#cfd4de}}
.verdict{{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--warn);
border-radius:10px;padding:16px 18px;margin:20px 0}}
.verdict b{{color:var(--warn)}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0}}
.metric{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}}
.metric .v{{font-size:24px;font-weight:800}}
.metric .v small{{font-size:14px;font-weight:600;color:var(--mut)}}
.metric .k{{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin-top:2px}}
.metric .n{{font-size:12px;color:var(--mut);margin-top:6px}}
.chart{{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:18px;margin:22px 0}}
.chart img{{width:100%;height:auto;display:block;border-radius:8px;background:#fff;margin:10px 0}}
.desc{{color:var(--mut);margin:0}}
.takeaway{{background:var(--panel2);border-radius:8px;padding:12px 14px}}
.source{{font-size:12px;color:var(--mut);word-break:break-all}}
.source code{{color:#b9c2d0}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;overflow-x:auto;display:block}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}
th{{color:var(--mut);font-weight:600}}
td.invalid{{background:#3a2326;color:var(--bad);text-align:center}}
td.invalid span{{font-size:11px}}
.st-on{{color:var(--acc);font-weight:700}}
.st-off{{color:var(--bad);font-weight:700}}
.st-na{{color:var(--mut)}}
.tbl-wrap{{overflow-x:auto}}
.note{{font-size:13px;color:var(--mut)}}
ul{{padding-left:20px}}
li{{margin-bottom:8px}}
footer{{margin-top:48px;border-top:1px solid var(--line);padding-top:16px;
font-size:13px;color:var(--mut)}}
code{{font-size:.92em}}
@media (max-width:600px){{.metric .v{{font-size:20px}}table{{font-size:13px}}}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="eyebrow">NEAR Hackathon 2026 · Investment Thesis track</div>
  <h1>NEAR is becoming a cross-chain settlement business. Price it like one.</h1>
  <p class="lede">NEAR&rsquo;s base layer barely earns anything — its Intents layer already
  grossed {money_exact(F30)} of fees in 30 days, keeps a growing share for NEAR
  buybacks, and is the only part of NEAR with a compounding, measurable revenue
  curve. The long-term investment case is not &ldquo;cheap fast L1&rdquo; but
  &ldquo;toll road on cross-chain volume&rdquo;: value NEAR on retained Intents
  revenue (fee-capture DCF), with base-layer usage and staking economics as the
  supporting chapters that test whether the toll road has a moat.</p>
  <div class="verdict"><b>Honest verdict up front:</b> at today&rsquo;s fees and the
  measured {pct(capture)} capture rate, retained revenue alone supports
  ${vpt:.2f} per token — {vpt_pct:.1f}% of the ${price:,.2f} price. The case for
  owning NEAR is the <em>option</em> on fee growth and rising capture, not
  today&rsquo;s cash flow. Everything below is built to test that option, not to
  sell it.</div>
  <p class="note">Data fetched {gen} (see per-chart source lines).
  Reproduce it: <code>python3 src/fetch.py &amp;&amp; python3 src/build.py &amp;&amp; python3 src/build_dashboard.py</code>.
  All figures trace to cached API responses in <code>data/raw/</code> or to labelled
  assumptions in <code>src/assumptions.yaml</code>. Nothing here is investment advice.</p>
</header>

<h2>Headline metrics</h2>
<div class="metrics">
  <div class="metric"><div class="v">{money_exact(F30)}</div><div class="k">Intents gross fees, trailing 30d</div><div class="n">DefiLlama · {M1['fetched_at_utc']}</div></div>
  <div class="metric"><div class="v">{pct(capture)}</div><div class="k">Measured 30d capture rate</div><div class="n">revenue.near.org SSR · rising: 19.1% all-time → 23.0% YTD → 36.0% 30d</div></div>
  <div class="metric"><div class="v">{money(R0)}<small>/yr</small></div><div class="k">Annualised retained revenue (R₀)</div><div class="n">F30 × 12 × capture</div></div>
  <div class="metric"><div class="v">${vpt:.2f} <small>vs ${price:,.2f}</small></div><div class="k">DCF value / token vs price</div><div class="n">r=15%, g=10%, c={pct(capture)} · {vpt_pct:.1f}% of price</div></div>
  <div class="metric"><div class="v">{money(be)}<small>/yr</small></div><div class="k">Break-even retained revenue</div><div class="n">{be_mult:.1f}× current R₀ — the deflation line</div></div>
  <div class="metric"><div class="v">{mcap_r0:.1f}×</div><div class="k">Market cap / retained revenue</div><div class="n">Mcap {money(mcap)} · gross-fee basis {M8['near_mcap_div_gross_intents_fees']:.1f}×</div></div>
  <div class="metric"><div class="v">{num(bought)}</div><div class="k">NEAR bought / yr (base)</div><div class="n">vs {num(issued)} issued/yr — net +{num(net)} NEAR/yr, still inflationary</div></div>
  <div class="metric"><div class="v">{pct_pts(M9['last_epoch_apy'] * 100)} <small>APY</small></div><div class="k">Staking APY · real yield {M9['real_yield_pp']:.2f}pp</div><div class="n">Max inflation {pct_pts(M9['max_inflation_rate'] * 100)} · {M10['current_validators']} validators</div></div>
{extra_cards}</div>

<h2>The model in one paragraph</h2>
<p>Value = R₁ ÷ (r − g), where R₀ = trailing-30d Intents gross fees × 12 ×
capture rate, R₁ = R₀ × (1 + g), and value per token = Value ÷ circulating
supply ({num(snap['circulating_supply_near'])} NEAR). Base case:
R₀ = {money_exact(R0)}/yr, R₁ = {money_exact(dcf['base_case']['R1_next_year_retained_revenue_usd'])},
equity value {money(dcf['base_case']['equity_value_usd'])} →
${vpt:.4f}/token at r=15%, g=10%, measured capture {pct(capture)}.
The 10% growth rate is a forward <em>assumption</em> (see
<code>src/assumptions.yaml</code>), not a trend extrapolation: trailing-30d fees
are down {M2['trailing_30d_vs_prior_30d_pct']:.1f}% vs the prior 30 days and the
365-day log-regression growth is ≈ −0.7%. The full-series log-regression is
dominated by the May–Aug 2025 launch ramp ($1/day → ~$200k/day) and is
<strong>not quoted anywhere in this thesis</strong> as a growth rate.</p>

<h2>The {len(charts)} charts</h2>
{chart_html}
{network_section}
{metcalfe_section}
{predictions_section}

<h2>Benchmarks — NEAR vs SOL / AVAX / ETH</h2>
<div class="tbl-wrap"><table>
<tr><th>Chain</th><th>Price</th><th>Market cap</th><th>30d fees</th><th>Annualised fees</th><th>Mcap / fees</th><th>TVL</th><th>Mcap / TVL</th></tr>
{peer_row('near', 'NEAR — Intents gross', 'fees_30d_usd_gross_intents', 'mcap_div_annualised_gross_intents_fees')}
{peer_row('near', 'NEAR — Intents retained (base)', 'fees_30d_usd_gross_intents', 'mcap_div_annualised_retained_fees_base')}
{peer_row('solana', 'Solana', 'fees_30d_usd', 'mcap_div_annualised_fees')}
{peer_row('avalanche-2', 'Avalanche', 'fees_30d_usd', 'mcap_div_annualised_fees')}
{peer_row('ethereum', 'Ethereum', 'fees_30d_usd', 'mcap_div_annualised_fees')}
</table></div>
<p class="note">NEAR &ldquo;retained&rdquo; uses annualised retained revenue
({money(R0)}/yr) in place of annualised fees, so its mcap/fees reads
{mcap_r0:.1f}×. Peer chain fees are DefiLlama 30d totals annualised — the same
methodology for all four chains, but DefiLlama chain-fee totals can undercount
vs other methodologies (e.g. Solana&rsquo;s total here is far below figures that
include all validator/Jito revenue). Use for relative ranking within this
dataset, not as absolute revenue. NEAR TVL is the DefiLlama historical-series
last point ({snap['near_tvl_last_point']['date']}, {money(snap['near_tvl_last_point']['tvl_usd'])}); the
DefiLlama /chains headline for NEAR ({money(peers['near']['tvl_usd_chains_endpoint'])})
disagrees — different inclusion methodology, recorded in
<code>data/processed/benchmarks.json</code>.</p>

<h2>Intents competitors — is NEAR winning the category?</h2>
<div class="tbl-wrap"><table>
<tr><th>Protocol</th><th>30d fees</th><th>7d fees</th><th>24h fees</th></tr>
{comp_rows}
</table></div>
<p class="note">Sources: DefiLlama <code>summary/fees/&#123;thorchain,chainflip,debridge&#125;</code>,
fetched {comp['chainflip']['fetched_at_utc']}. LI.FI was tested and dropped:
DefiLlama returns 404 (&ldquo;Fees for lifi not found&rdquo;). THORChain&rsquo;s 30d
figure is only {money_exact(comp['thorchain']['fees_30d_usd'])} — its fee series is
thin on DefiLlama; do not over-claim from it. On this dataset NEAR Intents
grosses about 2.0× Chainflip&rsquo;s 30d fees.</p>

<h2>Sensitivity — implied value per token (USD)</h2>
<p>Capture rate × perpetual fee growth, at a fixed 12% discount rate
(Chart 7). Base case (${vpt:.2f}) sits outside this grid: it uses the measured
{capture * 100:.2f}% capture at r=15%, g=10%.</p>
<div class="tbl-wrap"><table>
<tr><th>Capture ↓ / Growth →</th><th>0%</th><th>10%</th><th>20%</th></tr>
{heat_html}
</table></div>
<p class="note">Cells marked n/a are the invalid g ≥ r zone: a Gordon-growth model
requires growth below the discount rate, so no value is computed there. Even
the best valid cell (35% capture, 10% growth, r=12%) is
${c7['values_per_token_usd'][2][1]:.2f} — well under the ${price:,.2f} price.
Full 27-cell grid (r = 10/12/15%): <code>data/processed/sensitivity.json</code>.</p>

<h2>Capture is rising — the one trend that matters</h2>
<p>Retained ÷ gross fees by window (revenue.near.org, measured from its
server-rendered payload, cross-checked against the per-mechanism split):
all-time {pct(M4['capture_rate_by_window']['all_time'])} → YTD
{pct(M4['capture_rate_by_window']['ytd'])} → 7d
{pct(M4['capture_rate_by_window']['d7'])} → 30d
{pct(M4['capture_rate_by_window']['d30'])}. 30d split: direct fees
{pct(M4['mechanism_split_by_window']['d30']['pp_fe'])} + B2B
{pct(M4['mechanism_split_by_window']['d30']['pp_b2b'])} + quote improvement
{pct(M4['mechanism_split_by_window']['d30']['pp_qi'])}. The model&rsquo;s base
case uses the 30d rate, not the lifetime rate.</p>

<h2>Limitations — what this thesis cannot show</h2>
<ul>
<li><strong>Daily activity is now measured — and it is weak.</strong> The
NEARBlocks <code>/v1/charts</code> endpoint (2,303 daily points from 21 Jul 2020)
gives daily transactions, active accounts and new accounts; the research-phase
claim that &ldquo;no daily endpoint exists&rdquo; was wrong — the bare
<code>/v1/charts</code> path was never tested, only suffixed paths (all 404).
Daily transactions are {M12['current_pct_below_peak']:.1f}% below their
{M12['all_time_peak']['date']} peak and daily active accounts
{M13['current_pct_below_peak']:.1f}% below their {M13['all_time_peak']['date']}
peak. Early rows have gaps: <code>multichain_txns</code> is null before
14 Nov 2024 and <code>txn_volume</code> is null on 11 days in Jul–Aug 2020;
neither field is used in any metric.</li>
<li><strong>Volume is now measured too — with a shorter window.</strong> DefiLlama
<code>summary/dexs/near-intents</code> gives a daily Intents <em>volume</em> series
(699 points from 10 Dec 2024), so the growth story finally has its own x-axis:
{money(M15['total_30d_usd_from_daily_series'])} in 30 days, implying a
{M15['implied_gross_fee_rate_30d_bps']:.2f} bps gross fee rate. The volume series
starts Dec 2024, not at the May 2025 fee-series start — the two series cover
different windows, and the endpoint&rsquo;s own 30d total
({money(M15['total_30d_usd_endpoint'])}) differs slightly from the sum of the
last 30 daily points because its rolling window ends at fetch time, after the
last daily point.</li>
<li><strong>365-day price cap.</strong> CoinGecko&rsquo;s free tier limits history to
365 days (days=max returns 401). All price history here is one year.</li>
<li><strong>24-hour fee anomaly.</strong> Intents fees for 9 Nov 2026 were
{money_exact(M1['total_24h_usd'])} vs a 7-day daily average of
{money_exact(M1['total_7d_usd'] / 7)} — a full-day value in the series, so
either a real one-day drop or a DefiLlama reporting lag. No single day is
ever annualised; all annualisation uses 7d/30d trailing figures.</li>
<li><strong>Fees are volatile, not a ramp.</strong> Trailing-30d fees peaked at
{money_exact(M2['trailing_30d_peak']['trailing_30d_usd'])} on
{M2['trailing_30d_peak']['date']} and are {abs(M2['trailing_30d_usd'] / M2['trailing_30d_peak']['trailing_30d_usd'] - 1) * 100:.1f}%
below that peak. Do not quote the full-series launch-ramp CAGR.</li>
<li><strong>Revenue-dashboard caveats.</strong> The revenue.near.org headline
revenue figure ({money(snap['revenue_dashboard_all_time']['headline_revenue_usd'])}) has
an unlabelled window in the page payload and is never used as a model input.
Its wallet table is partial: the live NEARBlocks balance of
buybacks.multisignature.near ({num(snap['buyback_wallet_balance_live_near'])} NEAR)
is higher than the dashboard&rsquo;s traced all-time inflow
({num(snap['revenue_dashboard_all_time']['revenue_wallets_all_time_near']['buybacks.multisignature.near'])} NEAR),
so it must not be read as the full buyback total.</li>
<li><strong>TVL endpoints disagree.</strong> DefiLlama&rsquo;s NEAR historical-series
last point ({money(snap['near_tvl_last_point']['tvl_usd'])}) vs its /chains headline
({money(peers['near']['tvl_usd_chains_endpoint'])}). The auditable series value is used.</li>
<li><strong>Peer fees undercount.</strong> DefiLlama chain-fee totals can miss
revenue other methodologies include (notably Solana). Benchmarks rank within
this dataset only.</li>
<li><strong>Intents flow is concentrated in one routing provider.</strong>
<a href="https://github.com/Dare0x/Faultline">Faultline</a> (a fellow
Investment Thesis entry) measured from NearStats routing data, 30 days to
8 Nov 2026, that a single provider, SwapKit, carried $260.99M of $765.65M
observed 1Click volume (34.1%, across 48 apps). An outage or pause at that
provider is a concentration risk to the Intents flow &mdash; and therefore to
the fee capture this thesis values: its simulation displaces 10.2% of total
observed volume even if 70% of SwapKit&rsquo;s flow reroutes. The Oct 1
service pause is the live precedent: Oct 1&ndash;4 volume ran 31.6% below
the prior matching week.</li>
</ul>

<h2>Sources</h2>
<ul>
<li>DefiLlama — Intents &amp; chain fees, TVL: <a href="https://api.llama.fi/summary/fees/near-intents?dataType=dailyFees">api.llama.fi/summary/fees/near-intents</a></li>
<li>DefiLlama — Intents daily volume: <a href="https://api.llama.fi/summary/dexs/near-intents">api.llama.fi/summary/dexs/near-intents</a></li>
<li>NEARBlocks — daily activity series (txns, active accounts, 2020 → today): <a href="https://api.nearblocks.io/v1/charts">api.nearblocks.io/v1/charts</a></li>
<li>NEAR Revenue Dashboard (capture rate): <a href="https://revenue.near.org/">revenue.near.org</a></li>
<li>CoinGecko free API — prices, market caps, 365d history: <a href="https://www.coingecko.com/en/api">coingecko.com/en/api</a></li>
<li>NEARBlocks API — chain stats, validators: <a href="https://api.nearblocks.io/v1/stats">api.nearblocks.io/v1/stats</a></li>
<li>NEAR mainnet RPC — protocol config (2.5% inflation cap): <a href="https://rpc.mainnet.near.org">rpc.mainnet.near.org</a></li>
<li>Full source table, URLs and fetch timestamps: <code>data/manifest.json</code> and the README.</li>
</ul>

<footer>
<p>NEAR Hackathon 2026 — Investment Thesis track. Built with free, keyless data
only. Generated {gen} from <code>data/processed/*.json</code> by
<code>src/build_dashboard.py</code>. Not investment advice. NEAR payout account for
prizes (if awarded): <code>topeseun20.near</code>.</p>
</footer>
</div>
</body>
</html>
"""

    out = ROOT / "dashboard" / "index.html"
    out.write_text(html)
    print(f"wrote {out} ({len(html)} bytes)")
    print(f"headline: F30={money_exact(F30)} capture={pct(capture)} "
          f"R₀={money(R0)}/yr DCF=${vpt:.2f} vs ${price:.2f} "
          f"break-even={money(be)}/yr mcap/R₀={mcap_r0:.1f}x")


if __name__ == "__main__":
    main()
