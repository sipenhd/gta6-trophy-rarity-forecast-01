"""gta6-trophy-rarity-forecast-01: forecast Exophase earn rates for GTA VI's 55 PS5 trophies.

Method, in one paragraph: every trophy's earn rate is earners / players-tracked,
so the forecast is built in logit space from two views of the same history and
blended. (1) A recency-weighted straight line of logit(rate) against
ln(1 + hours since release) over the last 24 hours of reads, extrapolated to
the target with the slope damped and soft-shrunk by its own standard error,
because growth in logit space saturates as a game week ages and a straight
line only makes sense locally. (2) A physical
earners/tracked model: earners and players-tracked are each extrapolated on the
same log-time scale and divided again, which captures the dilution that hits
every rate when a wave of new players joins and Exophase refreshes its counts.
The median is a blend of the two; the quantile spread on the logit scale is a
random-walk term that grows with the horizon plus the fit's own residual plus an
extra refresh term, so a flat launch-night history (the practice cases, which
straddle Exophase's first refresh) gets a wide, downward-shifted band instead
of pretending nothing will move.

Standard library only, no network, deterministic: the same case always writes
the same bytes. Run: `python3 main.py` with MAKEFUN_INPUT_DIR / MAKEFUN_OUTPUT_DIR
set, else /input and /output.
"""

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
RELEASE = "2026-11-19T00:00:00Z"


def clamp(x: float) -> float:
    return min(99.99, max(0.01, x))


def logit(pct: float) -> float:
    p = clamp(pct)
    return math.log(p / (100 - p))


def sigmoid(lg: float) -> float:
    if lg >= 0:
        return 100 / (1 + math.exp(-lg))
    e = math.exp(lg)
    return 100 * e / (1 + e)


def round4(x: float):
    """Round to 4 decimals, half up (matches the starter's rounding)."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value.is_integer() else value


def parse_time(s: str) -> float:
    """ISO 8601 UTC -> epoch seconds (stdlib only)."""
    from datetime import datetime, timezone

    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def wls(xs, ys, ws):
    """Weighted least squares y ~ a + b*x. Returns (a, b, residual_sd, r2, se_b)."""
    sw = sum(ws)
    if sw <= 0 or len(xs) < 2:
        return None
    mx = sum(w * x for x, w in zip(xs, ws)) / sw
    my = sum(w * y for y, w in zip(ys, ws)) / sw
    sxx = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws))
    sxy = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws))
    if sxx <= 1e-12:
        return (my, 0.0, 0.0, 0.0, 0.0)
    b = sxy / sxx
    a = my - b * mx
    syy = sum(w * (y - my) ** 2 for y, w in zip(ys, ws))
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    var = sum(w * r * r for r, w in zip(resid, ws)) / sw
    r2 = 1 - (sum(w * r * r for r, w in zip(resid, ws)) / syy) if syy > 1e-12 else 0.0
    se_b = math.sqrt(max(var, 0.0) / sxx) if sxx > 0 else 0.0
    return (a, b, math.sqrt(max(var, 0.0)), max(0.0, min(1.0, r2)), se_b)


def shrink_slope(b, se_b):
    """Soft-shrink a slope toward 0 by its own standard error: a slope that
    is large next to its error survives, a noisy one is damped away."""
    if se_b <= 0:
        return b
    return b * abs(b) / (abs(b) + 1.5 * se_b)


def forecast_trophy(series, horizon_days, horizon_hours):
    """series: list of (hours_since_release, rate_pct, players_tracked).
    Returns (median_pct, sigma_logit)."""
    last_rate = series[-1][1]
    last_n = series[-1][2]
    rates = [r for _, r, _ in series]
    flat = max(rates) - min(rates) < 1e-9
    n_flat = all(n == last_n for _, _, n in series)

    # Fit only on reads where the trophy was actually earned: a printed 0.00%
    # is censored (true rate below half a hundredth), not logit(-9.2), and
    # early zero reads would drag every fit down.
    usable = [(t, r, n) for (t, r, n) in series if r > 0.005]
    if len(usable) < 3:
        usable = series
    # Local window: the last 24h of reads (the house curve baseline's window).
    # An adoption curve is S-shaped, so a straight line only makes sense
    # locally; the launch-night flat stretch must not set the slope. Extend
    # the window only when the last day holds too few reads.
    t_last = series[-1][0]
    for window in (24.0, 48.0, 1e9):
        pts = [(t, r, n) for (t, r, n) in usable if t >= t_last - window]
        if len(pts) >= 4 or window > 1e8:
            break
    xs = [math.log1p(max(t, 0.0)) for (t, _, _) in pts]
    ys = [logit(r) for (_, r, _) in pts]
    ws = [0.5 ** ((t_last - t) / 12.0) for (t, _, _) in pts]
    x_last = xs[-1]
    x_target = math.log1p(max(t_last + horizon_hours, 0.0))

    fit = wls(xs, ys, ws)
    if fit is None:
        return last_rate, 0.5 * math.sqrt(horizon_days)
    a, b, resid_sd, r2, se_b = fit

    b_s = shrink_slope(b, se_b)
    # Damp the extrapolation beyond the last read: growth saturates.
    x_eff = x_last + 0.7 * (x_target - x_last)
    med_logit = a + b_s * x_eff

    # Physical model: extrapolate earners and players-tracked separately.
    med2 = None
    try:
        es = [max(r * n / 100.0, 0.05) for (_, r, n) in pts]
        ns = [max(n, 1.0) for (_, _, n) in pts]
        fe = wls(xs, [math.log(e) for e in es], ws)
        fn = wls(xs, [math.log(n) for n in ns], ws)
        if fe is not None and fn is not None:
            ae, be, _, _, se_be = fe
            an, bn, _, _, se_bn = fn
            be_s = shrink_slope(be, se_be)
            bn_s = shrink_slope(bn, se_bn)
            e_t = math.exp(ae + be_s * x_eff)
            n_t = math.exp(an + bn_s * x_eff)
            if e_t > 0 and n_t > 0:
                med2 = logit(100.0 * e_t / n_t)
    except (ValueError, OverflowError):
        med2 = None

    if med2 is not None:
        med_logit = 0.6 * med_logit + 0.4 * med2

    # Sanity band: with no evidence of a collapse, the median should not sit
    # many logit units from the last read (the flat-history refresh branch
    # below is the one exception, and it sets its own shift).
    last_lg = logit(last_rate)
    med_logit = max(last_lg - 4.0, min(last_lg + 4.0, med_logit))

    # Spread on the logit scale.
    sigma = 0.5 * math.sqrt(horizon_days)
    sigma = math.sqrt(sigma * sigma + (resid_sd * 0.75) ** 2)
    if flat and n_flat and horizon_hours <= 6:
        # Launch-night practice shape: the page has not refreshed once in the
        # whole history, and Exophase's first refresh (documented in the kit's
        # RULES.txt) drops every rate but the 100% one as the tracked-player
        # count jumps. Expect a downward refresh and admit wide ignorance.
        med_logit += math.log(0.3)
        sigma = math.sqrt(sigma * sigma + 1.0 ** 2)
    elif flat:
        sigma = math.sqrt(sigma * sigma + 0.35 ** 2)
    if last_rate < 1.0:
        sigma = math.sqrt(sigma * sigma + 0.10 ** 2)
    sigma = max(0.3, min(1.8, sigma))
    return sigmoid(med_logit), sigma


def forecast_case(case: dict, name: str) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    if not case["history"]:
        raise ValueError(f"{name} has no history")
    t0 = parse_time(RELEASE)
    horizon_days = case["horizon_minutes"] / 1440.0
    horizon_hours = case["horizon_minutes"] / 60.0
    rows = []
    for i, trophy in enumerate(case["trophies"]):
        series = []
        for read in case["history"]:
            rate = read["rates"][i]
            if rate is None:
                continue
            t = (parse_time(read["at"]) - t0) / 3600.0
            series.append((t, float(rate), float(read["players_tracked"])))
        if not series:
            series = [(0.0, 0.01, 1.0)]
        median, sigma = forecast_trophy(series, horizon_days, horizon_hours)
        qs = []
        for z in Z:
            q = sigmoid(logit(median) + z * sigma)
            qs.append(round4(clamp(q)))
        # Keep quantiles non-decreasing after rounding.
        for k in range(1, 5):
            if qs[k] < qs[k - 1]:
                qs[k] = qs[k - 1]
        rows.append({"id": trophy["id"], "q": qs})
    rows.sort(key=lambda r: r["id"])
    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
