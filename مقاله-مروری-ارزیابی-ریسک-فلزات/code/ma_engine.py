# -*- coding: utf-8 -*-
"""Random-effects meta-analysis engine (REML, Hartung-Knapp-Sidik-Jonkman, prediction interval)."""
import math
import numpy as np
from scipy import optimize, stats


def combine_groups(groups):
    """Combine (n, mean, sd) groups into one (n, mean, sd) - Cochrane Handbook Table 6.5.a."""
    groups = [(n, m, s) for n, m, s in groups if n and m is not None and s is not None]
    n1, m1, s1 = groups[0]
    for n2, m2, s2 in groups[1:]:
        N = n1 + n2
        m = (n1 * m1 + n2 * m2) / N
        var = ((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2 + n1 * n2 / N * (m1 - m2) ** 2) / (N - 1)
        n1, m1, s1 = N, m, math.sqrt(var)
    return n1, m1, s1


def lognormal_moments(mean, sd, n):
    """Arithmetic mean/SD -> log-scale mean and its variance, assuming lognormality (Higgins et al. 2008)."""
    s2 = math.log(1.0 + (sd / mean) ** 2)
    mu = math.log(mean) - s2 / 2.0
    return mu, s2 / n, math.sqrt(s2)


def _reml_negll(tau2, y, v):
    w = 1.0 / (v + tau2)
    mu = np.sum(w * y) / np.sum(w)
    return 0.5 * (np.sum(np.log(v + tau2)) + math.log(np.sum(w)) + np.sum(w * (y - mu) ** 2))


def tau2_reml(y, v):
    hi = max(10.0, 10 * np.var(y, ddof=1) if len(y) > 1 else 10.0)
    res = optimize.minimize_scalar(_reml_negll, bounds=(0.0, hi), args=(y, v), method='bounded',
                                   options=dict(xatol=1e-12))
    t = float(res.x)
    # boundary check: REML maximum at zero
    if _reml_negll(0.0, y, v) <= _reml_negll(t, y, v):
        t = 0.0
    return t


def tau2_dl(y, v):
    w = 1.0 / v
    mu = np.sum(w * y) / np.sum(w)
    Q = np.sum(w * (y - mu) ** 2)
    c = np.sum(w) - np.sum(w ** 2) / np.sum(w)
    return max(0.0, (Q - (len(y) - 1)) / c)


def random_effects(y, v, method='REML', hksj=True, level=0.95):
    y = np.asarray(y, float)
    v = np.asarray(v, float)
    k = len(y)
    tau2 = tau2_reml(y, v) if method == 'REML' else tau2_dl(y, v)
    w = 1.0 / (v + tau2)
    mu = float(np.sum(w * y) / np.sum(w))
    se = math.sqrt(1.0 / np.sum(w))
    # heterogeneity (fixed-effect Q)
    wf = 1.0 / v
    mu_f = np.sum(wf * y) / np.sum(wf)
    Q = float(np.sum(wf * (y - mu_f) ** 2))
    df = k - 1
    pQ = float(1 - stats.chi2.cdf(Q, df)) if df > 0 else float('nan')
    I2 = max(0.0, (Q - df) / Q) * 100 if Q > 0 else 0.0
    if hksj and k > 1:
        q = float(np.sum(w * (y - mu) ** 2) / df)
        se_used = math.sqrt(max(q, 1.0) / np.sum(w))        # ad hoc variant: never narrower than the RE interval
        crit = stats.t.ppf(0.5 + level / 2, df)
    else:
        se_used = se
        crit = stats.norm.ppf(0.5 + level / 2)
    lo, hi = mu - crit * se_used, mu + crit * se_used
    if k > 2:
        tcrit = stats.t.ppf(0.5 + level / 2, k - 2)
        pi = (mu - tcrit * math.sqrt(tau2 + se_used ** 2), mu + tcrit * math.sqrt(tau2 + se_used ** 2))
    else:
        pi = (float('nan'), float('nan'))
    weights = w / np.sum(w) * 100
    return dict(k=k, mu=mu, se=se_used, ci=(lo, hi), pi=pi, tau2=tau2, tau=math.sqrt(tau2),
                Q=Q, df=df, pQ=pQ, I2=I2, weights=weights.tolist(), method=method, hksj=hksj)


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    # Validation against metafor's dat.bcg (log risk ratio), REML without Knapp-Hartung.
    bcg = [(4, 119, 11, 128), (6, 300, 29, 274), (3, 228, 11, 209), (62, 13536, 248, 12619),
           (33, 5036, 47, 5761), (180, 1361, 372, 1079), (8, 2537, 10, 619), (505, 87886, 499, 87892),
           (29, 7470, 45, 7232), (17, 1699, 65, 1600), (186, 50448, 141, 27197), (5, 2493, 3, 2338),
           (27, 16886, 29, 17825)]
    y, v = [], []
    for a, b, c, d in bcg:
        y.append(math.log((a / (a + b)) / (c / (c + d))))
        v.append(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
    r = random_effects(y, v, 'REML', hksj=False)
    print('BCG REML  estimate=%.4f se=%.4f tau2=%.4f I2=%.2f%%  Q=%.2f' % (r['mu'], r['se'], r['tau2'], r['I2'], r['Q']))
    print('metafor   estimate=-0.7145 se=0.1798 tau2=0.3132 I2=92.22%  Q=152.23')
    rd = random_effects(y, v, 'DL', hksj=False)
    print('BCG DL    estimate=%.4f tau2=%.4f   (metafor DL tau2=0.3088)' % (rd['mu'], rd['tau2']))
