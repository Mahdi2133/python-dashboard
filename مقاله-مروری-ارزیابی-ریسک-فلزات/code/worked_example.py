# -*- coding: utf-8 -*-
"""Illustrative application of the integrated equation to the one co-located dataset in the review:
Honghu Lake, China (S15, Zhang et al. 2017) - lake water and fish from the same lake.
Air: no co-located measurement; EU ambient target/limit values used as an upper-bound scenario."""
import json, math
import numpy as np
import integrated_hra as M
from ma_engine import combine_groups
import ma_data as D

BW, IRw, FIR = 61.6, 2.0, 0.05433            # kg; L/d (WHO default); kg/d (S15)
EF, ED, LT = 365, 30, 70
Cw = dict(As=0.990, Cd=0.140, Cr=1.630, Cu=3.090, Pb=3.420)       # µg/L, S15 Table 3
idx = dict(As=0, Cd=1, Cr=2, Cu=3, Pb=4)
Cf = {}
for m, i in idx.items():
    n, mean, sd = combine_groups([(g[0], g[1 + i][0], g[1 + i][1]) for g in D.S15_GROUPS.values()])
    Cf[m] = (mean * 1000, sd * 1000)          # µg/kg ww
Ca = dict(As=6.0, Cd=5.0, Pb=500.0)            # ng/m3, Directive 2004/107/EC target values; 2008/50/EC limit (Pb)

out = dict(params=dict(BW=BW, IRw=IRw, FIR=FIR, EF=EF, ED=ED, LT=LT), Cw=Cw, Cf=Cf, Ca=Ca, rows=[])


def run(metal_key, trv_key, label, with_air):
    c_a = Ca.get(metal_key, 0.0) if with_air else 0.0
    food = [dict(C=Cf[metal_key][0], IR=FIR)]
    Dw, Df, ECa, Da = M.doses(Cw[metal_key], food, c_a, IRw, BW, EF, ED, rr_inh=2.0)
    row = dict(metal=label, trv=trv_key, air=with_air, D_w=Dw, D_f=Df, EC_a=ECa, D_a=Da)
    t = M.TRV[trv_key]
    if t['rfd_w']:
        hq, hi, share = M.hazard(trv_key, Dw, Df, ECa)
        row.update(HQ=hq, HI=hi, share=share)
    if trv_key == 'iAs':
        row['MOE'] = M.moe(trv_key, Dw, Df, Da)
    if trv_key == 'Pb':
        row['MOE_SBP'] = M.moe(trv_key, Dw, Df, Da, bmdl=1.5)
        row['MOE_CKD'] = M.moe(trv_key, Dw, Df, Da, bmdl=0.63)
        row['share'] = dict(water=Dw / (Dw + Df + Da), food=Df / (Dw + Df + Da), air=Da / (Dw + Df + Da))
    if t['csf'] or t['iur']:
        Dw_c, Df_c, ECa_c, _ = M.doses(Cw[metal_key], food, c_a, IRw, BW, EF, ED, AT=LT)
        o, i, tot = M.cancer(trv_key, Dw_c, Df_c, ECa_c)
        row.update(ILCR_oral=o, ILCR_inh=i, ILCR=tot)
    out['rows'].append(row)
    return row


CASES = [('As', 'iAs', 'Inorganic As (fish total As as upper bound)'), ('Cd', 'Cd', 'Cd'),
         ('Cr', 'CrIII', 'Cr, all Cr(III) (lower bound)'), ('Cr', 'CrVI', 'Cr, all Cr(VI) (upper bound)'),
         ('Cu', 'Cu', 'Cu'), ('Pb', 'Pb', 'Pb')]
for with_air in (False, True):
    print('==== scenario', 'B (water + fish + air ceiling)' if with_air else 'A (water + fish, co-located)')
    for mk, tk, lab in CASES:
        r = run(mk, tk, lab, with_air)
        s = '%-44s Dw=%.4f Df=%.4f Da=%.4f' % (lab, r['D_w'], r['D_f'], r['D_a'])
        if 'HI' in r:
            s += ' | HI=%.3g share w/f/a=%s' % (r['HI'], '/'.join('%.0f%%' % (100 * v) if v is not None else '-'
                                                             for v in r['share'].values()))
        for k in ('MOE', 'MOE_SBP', 'MOE_CKD', 'ILCR'):
            if k in r:
                s += ' | %s=%.3g' % (k, r[k])
        print(s)

A = [r for r in out['rows'] if not r['air']]
hi_screen = sum(r['HI'] for r in A if 'HI' in r and 'lower bound' not in r['metal'])
out['HI_cumulative_screening_upper'] = hi_screen
print('scenario A cumulative screening HI (Cr as Cr(VI)) = %.3f' % hi_screen)

# context-specific water value for Cd (subtraction method, bounded 20-80 %)
cdA = [r for r in A if r['trv'] == 'Cd'][0]
D_other_water_equiv = cdA['D_f'] * M.TRV['Cd']['rfd_w'] / M.TRV['Cd']['rfd_f']
gv, p, p_used = M.allowable_water(M.TRV['Cd']['rfd_w'], BW, IRw, D_other_water_equiv)
out['Cd_context_water_value'] = dict(GV=gv, p_raw=p, p_used=p_used)
print('Cd context-specific water value = %.2f µg/L (raw allocation %.2f, bounded %.2f); WHO GV 3 µg/L' % (gv, p, p_used))
asA = [r for r in A if r['trv'] == 'iAs'][0]
gv, p, p_used = M.allowable_water(M.TRV['iAs']['rfd_w'], BW, IRw, asA['D_f'])
out['As_context_water_value'] = dict(GV=gv, p_raw=p, p_used=p_used)
print('iAs context-specific water value = %.2f µg/L (raw %.2f, bounded %.2f); WHO provisional GV 10 µg/L' % (gv, p, p_used))

# Monte Carlo on scenario A: independent vs correlated media (log-scale correlation rho)
mc = {}
for rho in (0.0, 0.6):
    spec = dict(Cw=(Cw['Cd'], Cw['Cd']), Cf=Cf['Cd'], IRw=(2.0, 0.8), IRf=(FIR, FIR * 0.8), BW=(61.6, 10.0), Ca=0.0)
    hi, dw, df = M.monte_carlo('Cd', spec, rho=rho)
    mc['Cd_HI_rho%.1f' % rho] = dict(P50=float(np.percentile(hi, 50)), P95=float(np.percentile(hi, 95)),
                                      P99=float(np.percentile(hi, 99)))
    if rho == 0.0:
        mc['Cd_rank_correlation'] = dict(Cw=M.spearman(dw, hi), Cf=M.spearman(df, hi))
    specp = dict(Cw=(Cw['Pb'], Cw['Pb']), Cf=Cf['Pb'], IRw=(2.0, 0.8), IRf=(FIR, FIR * 0.8), BW=(61.6, 10.0))
    _, dwp, dfp = M.monte_carlo('Cd', specp, rho=rho)       # sampler reused for doses only
    tot = dwp + dfp
    p95 = float(np.percentile(tot, 95))
    mc['Pb_dose_rho%.1f' % rho] = dict(P50=float(np.percentile(tot, 50)), P95=p95, MOE_SBP_P95=1.5 / p95,
                                        MOE_CKD_P95=0.63 / p95, water_share_median=float(np.median(dwp / tot)))
    # naive approach: sum of medium-specific P95s
    mc['Pb_sum_of_P95s_rho%.1f' % rho] = float(np.percentile(dwp, 95) + np.percentile(dfp, 95))
out['monte_carlo'] = mc
print(json.dumps(mc, indent=1))
json.dump(out, open('worked_example.json', 'w'), indent=1, default=float)
