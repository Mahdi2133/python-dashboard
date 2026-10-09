# -*- coding: utf-8 -*-
"""Pool metal concentrations in edible aquatic animal tissue (wet weight) across studies."""
import json, math, csv
import numpy as np
from ma_engine import combine_groups, lognormal_moments, random_effects
import ma_data as D

s10 = json.load(open('s10_parsed.json'))['summary']

def study_values(metal):
    """Return list of (study_id, n, mean_ugkg, sd_ugkg, note)."""
    out = []
    # S01, S02 direct
    for sid in ('S01', 'S02'):
        d = D.DIRECT[sid]
        if metal in d:
            m, s = d[metal]
            out.append((sid, d['n'], m, s, ''))
    # S10 canned fish (mg/kg -> µg/kg)
    if metal in s10:
        r = s10[metal]
        out.append(('S10', r['n'], r['mean'] * 1000, r['sd'] * 1000, 'across-product SD'))
    # S11 combine aquatic animal categories
    idx = {'Pb': 1, 'Cd': 2, 'As': 3, 'Hg': 4, 'MeHg': 5}
    if metal in idx:
        g = [(n, vals[idx[metal] - 1][0], vals[idx[metal] - 1][1]) for n, *vals in D.S11_GROUPS.values()]
        n, m, s = combine_groups(g)
        out.append(('S11', n, m * 1000, s * 1000, '%d categories combined' % len(g)))
    # S15 combine species
    idx15 = {'As': 0, 'Cd': 1, 'Cr': 2, 'Cu': 3, 'Pb': 4}
    if metal in idx15:
        g = [(n, vals[idx15[metal]][0], vals[idx15[metal]][1]) for n, *vals in D.S15_GROUPS.values()]
        n, m, s = combine_groups(g)
        note = 'BDL recorded as 0 in 5 of 6 species' if metal == 'As' else '6 species combined'
        out.append(('S15', n, m * 1000, s * 1000, note))
    return out


def analyse(metal, exclude=()):
    rows = [r for r in study_values(metal) if r[0] not in exclude]
    y, v, info = [], [], []
    for sid, n, m, s, note in rows:
        mu, var, sl = lognormal_moments(m, s, n)
        y.append(mu); v.append(var)
        info.append(dict(study=sid, label=D.STUDY_LABEL[sid], n=n, mean=m, sd=s, note=note,
                         gm=math.exp(mu), lo=math.exp(mu - 1.96 * math.sqrt(var)),
                         hi=math.exp(mu + 1.96 * math.sqrt(var))))
    res = random_effects(y, v, 'REML', hksj=True)
    for i, w in zip(info, res['weights']):
        i['weight'] = w
    pooled = dict(gm=math.exp(res['mu']), lo=math.exp(res['ci'][0]), hi=math.exp(res['ci'][1]),
                  pi_lo=math.exp(res['pi'][0]) if not math.isnan(res['pi'][0]) else None,
                  pi_hi=math.exp(res['pi'][1]) if not math.isnan(res['pi'][1]) else None)
    return info, res, pooled


if __name__ == '__main__':
    results = {}
    for metal in ('Pb', 'Cd', 'As'):
        info, res, pooled = analyse(metal)
        results[metal] = dict(studies=info, stats={k: res[k] for k in ('k', 'tau2', 'I2', 'Q', 'df', 'pQ')}, pooled=pooled)
        print('\n=== %s  (k=%d)  edible aquatic tissue, wet weight, µg/kg' % (metal, res['k']))
        for i in info:
            print('  %-4s n=%-4d mean=%9.2f sd=%9.2f  GM=%9.2f [%8.2f, %9.2f]  w=%5.1f%%  %s' %
                  (i['study'], i['n'], i['mean'], i['sd'], i['gm'], i['lo'], i['hi'], i['weight'], i['note']))
        print('  pooled GM = %.2f  95%% CI %.2f-%.2f  | 95%% PI %.2f-%.2f' %
              (pooled['gm'], pooled['lo'], pooled['hi'], pooled['pi_lo'], pooled['pi_hi']))
        print('  tau2=%.3f  I2=%.1f%%  Q=%.1f (df=%d, p=%.2g)' % (res['tau2'], res['I2'], res['Q'], res['df'], res['pQ']))

        # sensitivity: leave-one-out and pre-specified exclusions
        sens = []
        for sid in [i['study'] for i in info]:
            _, r2, p2 = analyse(metal, exclude=(sid,))
            sens.append(dict(excluded=sid, gm=p2['gm'], lo=p2['lo'], hi=p2['hi'], I2=r2['I2']))
            print('    leave-out %-4s -> GM %8.2f [%8.2f, %9.2f]  I2=%.1f%%' % (sid, p2['gm'], p2['lo'], p2['hi'], r2['I2']))
        results[metal]['leave_one_out'] = sens

    # descriptive only (k < 5): Hg, MeHg
    for metal in ('Hg', 'MeHg', 'Cr', 'Cu'):
        rows = study_values(metal)
        results[metal] = dict(descriptive=[dict(study=s, n=n, mean=m, sd=sd, note=no) for s, n, m, sd, no in rows])
        print('\n--- %s descriptive (k=%d): %s' % (metal, len(rows), ', '.join('%s %.1f' % (s, m) for s, n, m, sd, no in rows)))

    json.dump(results, open('ma_results.json', 'w'), indent=1, default=float)
    with open('ma_table.csv', 'w', newline='') as fh:
        wr = csv.writer(fh)
        wr.writerow(['metal', 'study', 'label', 'n', 'mean_ug_kg', 'sd_ug_kg', 'GM', 'CI_lo', 'CI_hi', 'weight_pct', 'note'])
        for metal in ('Pb', 'Cd', 'As'):
            for i in results[metal]['studies']:
                wr.writerow([metal, i['study'], i['label'], i['n'], round(i['mean'], 3), round(i['sd'], 3),
                             round(i['gm'], 3), round(i['lo'], 3), round(i['hi'], 3), round(i['weight'], 1), i['note']])
            p, st = results[metal]['pooled'], results[metal]['stats']
            wr.writerow([metal, 'POOLED', 'Random effects (REML, HKSJ)', '', '', '', round(p['gm'], 3), round(p['lo'], 3),
                         round(p['hi'], 3), 100, 'PI %.2f-%.2f; I2 %.1f%%; tau2 %.3f' % (p['pi_lo'], p['pi_hi'], st['I2'], st['tau2'])])
    print('\nwrote ma_results.json, ma_table.csv')
