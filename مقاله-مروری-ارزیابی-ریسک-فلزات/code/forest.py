# -*- coding: utf-8 -*-
"""Publication forest plots (one panel per metal) from ma_results.json."""
import json, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

INK, INK2, MUTED, GRID, ACCENT = '#0b0b0b', '#52514e', '#8a8984', '#e6e5e1', '#2a78d6'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8.5, 'axes.linewidth': 0.6,
                     'xtick.major.width': 0.6, 'xtick.minor.width': 0.4, 'xtick.color': INK2,
                     'axes.edgecolor': INK2, 'svg.fonttype': 'none', 'pdf.fonttype': 42})

R = json.load(open('ma_results.json'))
SHORT = {'S01': 'Wang 2024 · carp, CN', 'S02': 'Zhang 2023 · crayfish, CN', 'S10': 'Kosker 2023 · canned fish, TR',
         'S11': 'Kim 2023 · seafood, KR', 'S15': 'Zhang 2017 · lake fish, CN'}
NAMES = {'Pb': 'Lead (Pb)', 'Cd': 'Cadmium (Cd)', 'As': 'Total arsenic (As)'}


def fmt(x):
    if x is None: return '–'
    if x >= 1e5:
        e = int(math.floor(math.log10(x)))
        return '%.1f×10%s' % (x / 10 ** e, str(e).translate(str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')))
    if x >= 100: return '%.0f' % x
    if x >= 10: return '%.1f' % x
    if x >= 1: return '%.2f' % x
    return '%.2g' % x


def panel(fig, top, height, metal, letter):
    d = R[metal]
    st, po = d['stats'], d['pooled']
    studies = d['studies']
    k = len(studies)
    rows = k + 3                                   # studies, gap, pooled, PI
    # axes for the plot column; text columns are drawn in figure coordinates
    ax = fig.add_axes([0.46, top - height, 0.26, height])
    ax.set_xscale('log')
    ys = list(range(rows, rows - k, -1))
    lo_all = min([s['lo'] for s in studies] + [po['lo'], po['pi_lo'] or po['lo']])
    hi_all = max([s['hi'] for s in studies] + [po['hi'], po['pi_hi'] or po['hi']])
    xmin = 10 ** math.floor(math.log10(max(lo_all, 1e-3)))
    xmax = 10 ** math.ceil(math.log10(hi_all))
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(0.2, rows + 0.9)
    for s, y in zip(studies, ys):
        lo, hi = max(s['lo'], xmin), min(s['hi'], xmax)
        ax.plot([lo, hi], [y, y], color=INK2, lw=1.1, solid_capstyle='butt', zorder=2)
        size = 4 + 12 * math.sqrt(s['weight'] / 100)
        ax.plot(s['gm'], y, marker='s', ms=size, color=INK, mec='white', mew=0.8, zorder=3)
    # pooled diamond
    yp = 2.0
    dia = Polygon([[po['lo'], yp], [po['gm'], yp + 0.38], [po['hi'], yp], [po['gm'], yp - 0.38]],
                  closed=True, fc=ACCENT, ec=ACCENT, lw=0.8, zorder=3)
    ax.add_patch(dia)
    # prediction interval
    ypi = 1.0
    pl, ph = max(po['pi_lo'], xmin), min(po['pi_hi'], xmax)
    ax.plot([pl, ph], [ypi, ypi], color=ACCENT, lw=1.6, zorder=2)
    for x, clipped in ((pl, po['pi_lo'] < xmin), (ph, po['pi_hi'] > xmax)):
        if clipped:
            ax.annotate('', xy=(x, ypi), xytext=(x * (1.6 if x == pl else 1 / 1.6), ypi),
                        arrowprops=dict(arrowstyle='->', color=ACCENT, lw=1.2))
    ax.axvline(po['gm'], color=ACCENT, lw=0.6, ls=(0, (3, 3)), zorder=1)
    ax.set_yticks([])
    for sp in ('left', 'right', 'top'):
        ax.spines[sp].set_visible(False)
    ax.grid(axis='x', which='major', color=GRID, lw=0.6, zorder=0)
    ax.set_xlabel('Geometric mean, µg/kg wet weight (log scale)', color=INK2, fontsize=8)

    # text columns -------------------------------------------------------
    def y2fig(y):
        return top - height + height * (y - 0.2) / (rows + 0.9 - 0.2)

    hdr_y = y2fig(rows + 0.9) + 0.004
    cols = [(0.02, 'Study · matrix, country', 'left'), (0.315, 'n', 'right'), (0.435, 'Mean ± SD', 'right'),
            (0.86, 'GM [95% CI]', 'right'), (0.975, 'Weight', 'right')]
    fig.text(0.02, hdr_y + 0.03, '%s  %s' % (letter, NAMES[metal]), fontsize=10, fontweight='bold', color=INK)
    for x, t, ha in cols:
        fig.text(x, hdr_y, t, ha=ha, va='bottom', fontsize=8, fontweight='bold', color=INK2)
    for s, y in zip(studies, ys):
        yy = y2fig(y)
        fig.text(0.02, yy, SHORT[s['study']], va='center', color=INK)
        fig.text(0.315, yy, '%d' % s['n'], va='center', ha='right', color=INK)
        fig.text(0.435, yy, '%s ± %s' % (fmt(s['mean']), fmt(s['sd'])), va='center', ha='right', color=INK)
        fig.text(0.86, yy, '%s [%s, %s]' % (fmt(s['gm']), fmt(s['lo']), fmt(s['hi'])), va='center', ha='right', color=INK)
        fig.text(0.975, yy, '%.1f%%' % s['weight'], va='center', ha='right', color=INK)
    fig.text(0.02, y2fig(yp), 'Random-effects model (REML, HKSJ)', va='center', fontweight='bold', color=INK)
    fig.text(0.86, y2fig(yp), '%s [%s, %s]' % (fmt(po['gm']), fmt(po['lo']), fmt(po['hi'])),
             va='center', ha='right', fontweight='bold', color=INK)
    fig.text(0.975, y2fig(yp), '100%', va='center', ha='right', fontweight='bold', color=INK)
    fig.text(0.02, y2fig(ypi), '95% prediction interval', va='center', color=INK2)
    fig.text(0.86, y2fig(ypi), '[%s, %s]' % (fmt(po['pi_lo']), fmt(po['pi_hi'])), va='center', ha='right', color=INK2)
    het = ('Heterogeneity: τ² = %.2f;  I² = %.1f%%;  Q = %.0f (df = %d), p < 0.001'
           % (st['tau2'], st['I2'], st['Q'], st['df']))
    fig.text(0.02, top - height - 0.052, het, fontsize=7.8, color=INK2)


fig = plt.figure(figsize=(7.2, 10.2))
H, gap, top = 0.19, 0.11, 0.935
for i, (metal, letter) in enumerate((('Pb', 'A'), ('Cd', 'B'), ('As', 'C'))):
    panel(fig, top - i * (H + gap + 0.003), H, metal, letter)
fig.text(0.02, 0.008, 'Squares: study geometric means (size ∝ weight); lines: 95% CI (hidden where narrower than the square).\n'
         'Diamond: pooled geometric mean with Hartung–Knapp–Sidik–Jonkman 95% CI. Blue bar: 95% prediction interval.\n'
         'Log-normal moments derived from the reported arithmetic mean and SD (Higgins et al., 2008).\n'
         'Country codes: CN China, TR Türkiye, KR Republic of Korea. Mean ± SD in µg/kg wet weight.',
         fontsize=7, color=INK2, linespacing=1.4)
for ext in ('png', 'pdf', 'svg'):
    fig.savefig('fig_forest.%s' % ext, dpi=300)
print('saved fig_forest.png/.pdf/.svg')
