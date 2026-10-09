# -*- coding: utf-8 -*-
"""Figures 1, 2, 4 and 5 of the revised manuscript."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.transforms
from matplotlib.patches import FancyBboxPatch, Rectangle

INK, INK2, MUTED, GRID = '#0b0b0b', '#52514e', '#8a8984', '#e6e5e1'
WATER, FOOD, AIR, DUST = '#2a78d6', '#eb6834', '#1baf7a', '#8a8984'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8.5, 'axes.linewidth': 0.6,
                     'axes.edgecolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
                     'svg.fonttype': 'none', 'pdf.fonttype': 42})


def save(fig, name):
    for ext in ('png', 'pdf'):
        fig.savefig('%s.%s' % (name, ext), dpi=300)
    plt.close(fig)
    print('saved', name)


# ---------------------------------------------------------------------------
# Figure 1 - PRISMA 2020 flow
def box(ax, x, y, w, h, text, bold=False, fc='white', ec=INK2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.004,rounding_size=0.01', fc=fc, ec=ec, lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha='center', va='center', fontsize=8, color=INK,
            fontweight='bold' if bold else 'normal', linespacing=1.35)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle='-|>', color=INK2, lw=0.8))


fig = plt.figure(figsize=(7.2, 6.4))
ax = fig.add_axes([0, 0, 1, 1]); ax.axis('off'); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
for y, lab in ((0.86, 'Identification'), (0.56, 'Screening'), (0.12, 'Included')):
    ax.text(0.025, y, lab, rotation=90, ha='center', va='center', fontsize=9, fontweight='bold', color=INK2)
L, W, R, WR = 0.06, 0.40, 0.55, 0.42
box(ax, L, 0.82, W, 0.13, 'Records identified from databases\n(PubMed, Web of Science, Embase,\nScopus; to 30 Nov 2024)\nn = 5,499')
box(ax, R, 0.84, WR, 0.09, 'Duplicates removed before screening\nn = 1,880')
box(ax, L, 0.66, W, 0.08, 'Records screened (title/abstract)\nn = 3,619')
box(ax, R, 0.66, WR, 0.08, 'Records excluded\nn = 3,534')
box(ax, L, 0.50, W, 0.08, 'Full-text reports assessed\nn = 85')
box(ax, R, 0.47, WR, 0.14, 'Reports excluded at full text\nn = 70\n(reasons and counts in Table S6;\ncategory counts must sum to 70)')
box(ax, L, 0.34, W, 0.08, 'Judged eligible, first round\nn = 15')
box(ax, R, 0.31, WR, 0.14, 'Removed at re-screening (criteria b, c)\nn = 2\n(instrument-validation study S05;\nspiked pot experiment S08)')
box(ax, L, 0.18, W, 0.08, 'Studies meeting criteria\nn = 13')
box(ax, R, 0.18, WR, 0.08, 'Awaiting full-text verification\nn = 1 (S06, PDF not retrieved)')
box(ax, L, 0.03, W, 0.09, 'Included in qualitative synthesis  n = 12\nIncluded in meta-analysis  n = 5', bold=True,
    fc='#eef4fc', ec=WATER)
for y1, y2 in ((0.82, 0.74), (0.66, 0.58), (0.50, 0.42), (0.34, 0.26), (0.18, 0.12)):
    arrow(ax, L + W / 2, y1, L + W / 2, y2)
for yb, ybox in ((0.885, 0.885), (0.70, 0.70), (0.54, 0.54), (0.38, 0.38), (0.22, 0.22)):
    arrow(ax, L + W, yb, R, ybox)
save(fig, 'fig1_prisma')

# ---------------------------------------------------------------------------
# Figure 2 - evidence map (study x metal; marker per medium)
studies = ['S01', 'S02', 'S03', 'S04', 'S07', 'S09', 'S10', 'S11', 'S12', 'S13', 'S14', 'S15']
labels = {'S01': 'S01 Wang 2024 · CN', 'S02': 'S02 Zhang 2023 · CN', 'S03': 'S03 Torabi 2023 · IR †',
          'S04': 'S04 Semerjian 2024 · AE', 'S07': 'S07 Hoque 2024 · BD', 'S09': 'S09 Rahman 2022 · BD',
          'S10': 'S10 Kosker 2023 · TR', 'S11': 'S11 Kim 2023 · KR', 'S12': 'S12 Senoro 2022 · PH',
          'S13': 'S13 Zhang 2019 · CN', 'S14': 'S14 Senoro 2023 · PH', 'S15': 'S15 Zhang 2017 · CN'}
metals = ['As', 'Cd', 'Pb', 'Hg', 'Cr', 'Ni', 'Cu', 'Zn', 'Fe', 'Mn', 'Al', 'Ba', 'Co', 'Se']
cov = {  # from workbook sheet 05_EvidenceMap; medium codes w=drinking/domestic water, f=food, d=street dust
    'S01': {'f': 'As Cd Cr Cu Ni Pb'}, 'S02': {'f': 'As Cd Cu Hg Pb'}, 'S03': {'f': 'Cd Cu Ni Pb Zn'},
    'S04': {'d': 'As Cd Cr Cu Fe Mn Ni Pb Zn'}, 'S07': {'w': 'As Cd Cr Cu Fe Mn Zn'},
    'S09': {'f': 'As Cr Pb'}, 'S10': {'f': 'Al As Cd Cr Cu Fe Pb Se Zn'}, 'S11': {'f': 'As Cd Hg Pb'},
    'S12': {'w': 'As Ba Cu Fe Mn Ni Pb Zn'}, 'S13': {'d': 'As Cd Co Cr Cu Hg Mn Ni Pb Zn'},
    'S14': {'w': 'As Ba Cr Cu Fe Mn Ni Pb Zn'}, 'S15': {'f': 'As Cd Cr Cu Pb Zn'}}
colocated = {'S09': 'As Cr Pb', 'S15': 'As Cd Cr Cu Pb Zn'}   # environmental (non-drinking) water at the same site
fig = plt.figure(figsize=(7.2, 4.6))
ax = fig.add_axes([0.25, 0.17, 0.73, 0.72])
off = {'w': -0.22, 'f': 0.0, 'd': 0.22}
col = {'w': WATER, 'f': FOOD, 'd': DUST}
for i, s in enumerate(studies):
    y = len(studies) - 1 - i
    if i % 2 == 0:
        ax.add_patch(Rectangle((-0.5, y - 0.5), len(metals), 1, fc='#f6f6f4', ec='none', zorder=0))
    for med, ms in cov[s].items():
        for m in ms.split():
            ax.plot(metals.index(m) + off[med], y, 's', ms=6.2, color=col[med], mec='white', mew=0.6, zorder=3)
    for m in colocated.get(s, '').split():
        ax.plot(metals.index(m) + off['w'], y, 's', ms=5.4, mfc='white', mec=WATER, mew=1.1, zorder=3)
ax.set_xlim(-0.5, len(metals) - 0.5); ax.set_ylim(-0.6, len(studies) - 0.4)
ax.set_xticks(range(len(metals))); ax.set_xticklabels(metals, fontsize=8.5, color=INK)
ax.xaxis.tick_top()
ax.set_yticks(range(len(studies))); ax.set_yticklabels([labels[s] for s in reversed(studies)], fontsize=8, color=INK)
ax.tick_params(length=0)
for sp in ax.spines.values():
    sp.set_visible(False)
for x in range(len(metals) - 1):
    ax.axvline(x + 0.5, color=GRID, lw=0.6, zorder=1)
h = [plt.Line2D([], [], ls='', marker='s', ms=6.5, color=WATER, mec='white', label='Drinking/domestic water'),
     plt.Line2D([], [], ls='', marker='s', ms=6.5, color=FOOD, mec='white', label='Food as consumed'),
     plt.Line2D([], [], ls='', marker='s', ms=6.5, color=DUST, mec='white', label='Settled street dust'),
     plt.Line2D([], [], ls='', marker='s', ms=6, mfc='white', mec=WATER, mew=1.1,
                label='Co-located surface/pond water (not drinking water)')]
fig.legend(handles=h, loc='lower left', bbox_to_anchor=(0.02, 0.0), ncol=2, frameon=False, fontsize=7.8,
           handletextpad=0.3, columnspacing=1.4)
fig.text(0.02, 0.955, 'No study measured ambient air. † preprint values fail internal consistency checks (excluded from pooling).',
         fontsize=7.4, color=INK2)
save(fig, 'fig2_evidence_map')

# ---------------------------------------------------------------------------
# Figure 4 - integrated framework schematic
fig = plt.figure(figsize=(7.2, 5.4))
ax = fig.add_axes([0, 0, 1, 1]); ax.axis('off'); ax.set_xlim(0, 1); ax.set_ylim(0, 1)


def tbox(x, y, w, h, title, body, ec):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.004,rounding_size=0.012', fc='white', ec=ec, lw=1.0))
    ax.add_patch(Rectangle((x, y + h - 0.004), w, 0.004, fc=ec, ec='none'))
    ax.text(x + 0.012, y + h - 0.03, title, fontsize=8.4, fontweight='bold', color=INK, va='top')
    ax.text(x + 0.012, y + h - 0.075, body, fontsize=7.6, color=INK2, va='top', linespacing=1.45)


ax.text(0.02, 0.965, '1  Co-located measurements (same population, place, period)', fontsize=9, fontweight='bold', color=INK)
tbox(0.02, 0.70, 0.30, 0.235, 'Drinking water', 'C_w  (µg/L)\nIR_w  (L/d)\ntreated-water basis\n<LOD: LOD/2 or ROS', WATER)
tbox(0.35, 0.70, 0.30, 0.235, 'Diet (k food groups)', 'C_k  (µg/kg wet wt, as eaten)\nIR_k  (kg/d)\nS_k  toxic-species fraction\nRBA_k  relative bioavailability', FOOD)
tbox(0.68, 0.70, 0.30, 0.235, 'Ambient air', 'C_a  (ng/m³, PM10)\nET, EF  time-activity\nRfC / IUR basis\n(RAGS Part F)', AIR)
ax.text(0.02, 0.645, '2  Route doses on a common scale', fontsize=9, fontweight='bold', color=INK)
ax.add_patch(FancyBboxPatch((0.02, 0.47), 0.96, 0.15, boxstyle='round,pad=0.004,rounding_size=0.012', fc='#f6f6f4', ec=GRID))
ax.text(0.5, 0.567, 'D_w = C_w·IR_w·EF·ED / (BW·AT)          D_f = Σ_k C_k·S_k·RBA_k·IR_k·EF·ED / (BW·AT)          '
        'EC_a = C_a·ET·EF·ED / AT', ha='center', fontsize=7.6, color=INK)
ax.text(0.5, 0.505, 'population-specific BW, IR, EF, ED;  joint distribution sampled by Monte Carlo with inter-media correlation ρ',
        ha='center', fontsize=7.4, color=INK2, style='italic')
ax.text(0.02, 0.425, '3  One aggregate index per metal, chosen by mode of action', fontsize=9, fontweight='bold', color=INK)
tbox(0.02, 0.18, 0.30, 0.225, 'Threshold agents', 'HI_agg = D_w/RfD_w + D_f/RfD_f\n            + EC_a/RfC\nCd, Cr, Cu, Hg, Ni, iAs\nflag when HI_agg > 1', INK2)
tbox(0.35, 0.18, 0.30, 0.225, 'Non-threshold agents', 'MOE = BMDL / (D_w + D_f + D_a,eq)\nPb (BMDL01/10), iAs (BMDL05)\nconcern when MOE ≤ 1\n(≥ 10 reassuring: SBP, CKD)', INK2)
tbox(0.68, 0.18, 0.30, 0.225, 'Carcinogens', 'ILCR = (D_w + D_f)·CSF\n          + EC_a·IUR\niAs, Cr(VI), Cd/Ni (inh.), Pb\nlifetime AT; ADAF for Cr(VI)', INK2)
ax.text(0.02, 0.135, '4  Outputs', fontsize=9, fontweight='bold', color=INK)
ax.text(0.02, 0.095, '•  empirical source contribution  f_m = HQ_m / HI_agg   (replaces the default 20 % RSC)', fontsize=7.8, color=INK)
ax.text(0.02, 0.060, '•  context-specific water value  C*_w = RfD·BW·P / IR_w,  P = clamp(1 − D_other/RfD, 0.2, 0.8)', fontsize=7.8, color=INK)
ax.text(0.02, 0.025, '•  target-organ HI across metals;  P50 / P95 of the aggregate (not the sum of route-specific P95s)', fontsize=7.8, color=INK)
save(fig, 'fig4_framework')

# ---------------------------------------------------------------------------
# Figure 5 - worked example: medium contribution per metal, scenarios A and B
W = json.load(open('worked_example.json'))
rows = W['rows']
order = [('iAs', 'Inorganic As', 'HI'), ('Cd', 'Cd', 'HI'), ('CrVI', 'Cr as Cr(VI)', 'HI'), ('Cu', 'Cu', 'HI'),
         ('Pb', 'Pb (dose share)', 'MOE_CKD')]
fig = plt.figure(figsize=(7.2, 4.4))
ax = fig.add_axes([0.2, 0.2, 0.56, 0.72])
yt, yl = [], []
y = 0
for trv, name, metric in order:
    for air in (False, True):
        r = [q for q in rows if q['trv'] == trv and q['air'] == air][0]
        sh = r['share']
        left = 0
        for med, c in (('water', WATER), ('food', FOOD), ('air', AIR)):
            v = sh.get(med) or 0.0
            if v > 0:
                ax.barh(y, v * 100, left=left, height=0.62, color=c, ec='white', lw=1.0,
                        hatch='////' if med == 'air' else None)
            left += v * 100
        val = r[metric]
        txt = ('HI %.3g' % val) if metric == 'HI' else ('MOE(CKD) %.2g' % val)
        ax.text(1.02, y, txt, transform=matplotlib.transforms.blended_transform_factory(ax.transAxes, ax.transData),
                va='center', fontsize=7.8, color=INK)
        yt.append(y); yl.append('%s · %s' % (name, 'B' if air else 'A'))
        y -= 0.85
    y -= 0.45
ax.set_yticks(yt); ax.set_yticklabels(yl, fontsize=8, color=INK)
ax.set_xlim(0, 100); ax.set_xlabel('Share of aggregate hazard index (Pb: of total dose), %', color=INK2, fontsize=8)
ax.tick_params(axis='y', length=0)
for sp in ('top', 'right', 'left'):
    ax.spines[sp].set_visible(False)
ax.grid(axis='x', color=GRID, lw=0.6); ax.set_axisbelow(True)
h = [Rectangle((0, 0), 1, 1, fc=WATER, ec='white', label='Water (measured)'),
     Rectangle((0, 0), 1, 1, fc=FOOD, ec='white', label='Fish (measured)'),
     Rectangle((0, 0), 1, 1, fc=AIR, ec='white', hatch='////', label='Air (EU target value, scenario)')]
fig.legend(handles=h, loc='lower left', bbox_to_anchor=(0.2, 0.0), ncol=3, frameon=False, fontsize=7.8)
fig.text(0.02, 0.955, 'Honghu Lake (S15): A = water + fish, co-located;  B = A + air at the EU target/limit value',
         fontsize=8, color=INK2)
save(fig, 'fig5_worked_example')
