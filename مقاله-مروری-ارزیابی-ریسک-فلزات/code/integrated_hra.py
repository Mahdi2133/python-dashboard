# -*- coding: utf-8 -*-
"""Integrated multi-pathway (water + food + air) health risk model for metals.

Units used throughout
    C_w  drinking water          µg/L
    C_k  food item k (as eaten)  µg/kg wet weight
    C_a  air (PM10 / total)      ng/m3
    dose                         µg/kg bw/day
    RfD, BMDL                    µg/kg bw/day
    RfC                          µg/m3
    CSF                          (µg/kg bw/day)^-1
    IUR                          (µg/m3)^-1
"""
import math
import numpy as np

# ---------------------------------------------------------------------------
# Toxicity reference values (verified October 2026; see Table 3 of the manuscript)
TRV = {
    # metal: oral RfD water, oral RfD food, RfC, CSF oral, IUR, BMDL (non-threshold)
    'iAs':   dict(rfd_w=0.06, rfd_f=0.06, rfc=0.015, csf=32e-3, iur=4.3e-3, bmdl=0.06,
                  src='US EPA IRIS 2025 (RfD 6e-5 mg/kg-d, CSF 32 per mg/kg-d); OEHHA REL 0.015 µg/m3; '
                      'IRIS IUR 4.3e-3; EFSA 2024 BMDL05 0.06 µg/kg-d'),
    'Cd':    dict(rfd_w=0.5, rfd_f=1.0, rfc=0.01, csf=None, iur=1.8e-3, bmdl=None,
                  src='US EPA IRIS (water 5e-4, food 1e-3 mg/kg-d); ATSDR chronic inhalation MRL 1e-5 mg/m3; IRIS IUR 1.8e-3'),
    'CrVI':  dict(rfd_w=0.9, rfd_f=0.9, rfc=0.03, csf=0.26e-3, iur=1.8e-2, bmdl=None,
                  src='US EPA IRIS 2024 (RfD 9e-4 mg/kg-d; RfC 3e-5 mg/m3; OSF 0.26 per mg/kg-d with ADAFs; IUR 1.8e-2)'),
    'CrIII': dict(rfd_w=1500.0, rfd_f=1500.0, rfc=None, csf=None, iur=None, bmdl=None,
                  src='US EPA IRIS (insoluble salts) 1.5 mg/kg-d'),
    'Cu':    dict(rfd_w=40.0, rfd_f=40.0, rfc=None, csf=None, iur=None, bmdl=None,
                  src='US EPA HEAST 4e-2 mg/kg-d (EFSA 2023 ADI 0.07 mg/kg-d)'),
    'Pb':    dict(rfd_w=None, rfd_f=None, rfc=None, csf=8.5e-6, iur=1.2e-5, bmdl=0.5,
                  src='No RfD (EPA); EFSA 2010 BMDL01 0.50 (neurodevelopment), 1.50 (SBP), BMDL10 0.63 (CKD) µg/kg-d; '
                      'OEHHA CSF 8.5e-3 per mg/kg-d, IUR 1.2e-5'),
}


# ---------------------------------------------------------------------------
def time_factor(EF, ED, AT_years):
    """EF (d/y) * ED (y) / AT (d)."""
    return EF * ED / (AT_years * 365.0)


def doses(Cw, foods, Ca, IRw, BW, EF=365, ED=30, AT=None, InhR=20.0, rr_inh=1.0):
    """Route-specific average daily doses (µg/kg-d) and exposure concentration (µg/m3).

    foods: list of dicts {C (µg/kg ww), IR (kg/d), S (toxic-species fraction), RBA (relative bioavailability)}
    rr_inh: route-to-route factor converting inhaled dose to an oral-equivalent dose (MOE only)
    """
    AT = ED if AT is None else AT
    tf = time_factor(EF, ED, AT)
    D_w = Cw * IRw / BW * tf
    D_f = sum(f['C'] * f.get('S', 1.0) * f.get('RBA', 1.0) * f['IR'] for f in foods) / BW * tf
    EC_a = Ca / 1000.0 * tf                      # ng/m3 -> µg/m3, time-weighted (ET = 24 h)
    D_a = Ca / 1000.0 * InhR / BW * tf * rr_inh  # oral-equivalent inhaled dose
    return D_w, D_f, EC_a, D_a


def hazard(metal, D_w, D_f, EC_a):
    t = TRV[metal]
    hq = dict(water=D_w / t['rfd_w'] if t['rfd_w'] else None,
              food=D_f / t['rfd_f'] if t['rfd_f'] else None,
              air=EC_a / t['rfc'] if (t['rfc'] and EC_a) else (0.0 if t['rfc'] else None))
    vals = [v for v in hq.values() if v is not None]
    hi = sum(vals) if vals else None
    share = {k: (v / hi if (v is not None and hi) else None) for k, v in hq.items()}
    return hq, hi, share


def cancer(metal, D_w_c, D_f_c, EC_a_c):
    t = TRV[metal]
    oral = (D_w_c + D_f_c) * t['csf'] if t['csf'] else 0.0
    inh = EC_a_c * t['iur'] if t['iur'] else 0.0
    return oral, inh, oral + inh


def moe(metal, D_w, D_f, D_a, bmdl=None):
    b = bmdl or TRV[metal]['bmdl']
    tot = D_w + D_f + D_a
    return b / tot if tot > 0 else float('inf')


def allowable_water(rfd, BW, IRw, D_other, floor=0.2, ceiling=0.8):
    """Context-specific drinking-water value (µg/L): subtraction method bounded by WHO/EPA 20-80 % allocation."""
    p = 1.0 - D_other / rfd                     # fraction of the RfD left for water
    p_used = min(max(p, floor), ceiling)
    return rfd * BW * p_used / IRw, p, p_used


# ---------------------------------------------------------------------------
# Monte Carlo with inter-media correlation (Gaussian copula on log scale)
def lognorm_params(mean, sd):
    s2 = math.log(1 + (sd / mean) ** 2)
    return math.log(mean) - s2 / 2, math.sqrt(s2)


def monte_carlo(metal, spec, n=100_000, rho=0.0, seed=1):
    """spec: dict with (mean, sd) for Cw, Cf, IRw, IRf, BW (normal) and fixed Ca.
    rho: correlation between log Cw and log Cf (common-source covariance)."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, 2))
    z2 = rho * z[:, 0] + math.sqrt(1 - rho ** 2) * z[:, 1]
    mw, sw = lognorm_params(*spec['Cw'])
    mf, sf = lognorm_params(*spec['Cf'])
    Cw = np.exp(mw + sw * z[:, 0])
    Cf = np.exp(mf + sf * z2)
    IRw = np.exp(np.random.default_rng(seed + 1).normal(*lognorm_params(*spec['IRw']), n))
    IRf = np.exp(np.random.default_rng(seed + 2).normal(*lognorm_params(*spec['IRf']), n))
    BW = np.clip(np.random.default_rng(seed + 3).normal(*spec['BW'], n), 30, None)
    t = TRV[metal]
    D_w = Cw * IRw / BW
    D_f = Cf * spec.get('S', 1.0) * IRf / BW
    EC_a = spec.get('Ca', 0.0) / 1000.0
    hi = D_w / t['rfd_w'] + D_f / t['rfd_f'] + (EC_a / t['rfc'] if t['rfc'] else 0.0)
    return hi, D_w, D_f


def spearman(x, y):
    rx = np.argsort(np.argsort(x))
    ry = np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])
