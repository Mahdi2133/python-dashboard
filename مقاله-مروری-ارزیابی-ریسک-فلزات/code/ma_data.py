# -*- coding: utf-8 -*-
"""Meta-analysis input data: edible aquatic animal tissue, wet-weight basis (µg/kg).

Every value is traced to a table or text passage in the source paper.  One
estimate per study per metal; where a study reports several groups (species or
product categories) they are combined into a single study-level mean and SD with
the standard formula for combining groups (Cochrane Handbook, Table 6.5.a).
"""

# ---------------------------------------------------------------------------
# S11  Kim et al. 2023, Foods (South Korea) - Table 4, mg/kg wet weight,
#      mean with SD in parentheses; n per category from Section 2.1 / Table 1.
#      Sea algae is excluded (not animal tissue).
S11_GROUPS = {
    #                n     Pb mean, sd      Cd mean, sd      As mean, sd      Hg mean, sd       MeHg mean, sd
    'freshwater fish': (87,  (0.012, 0.018), (0.003, 0.010), (0.151, 0.260), (0.066, 0.108), (0.023, 0.066)),
    'marine fish':     (559, (0.014, 0.030), (0.013, 0.027), (1.776, 2.828), (0.205, 0.639), (0.035, 0.111)),
    'crustaceans':     (65,  (0.041, 0.143), (0.180, 0.505), (2.969, 3.143), (0.021, 0.035), (0.004, 0.008)),
    'mollusks':        (320, (0.067, 0.114), (0.202, 0.334), (3.272, 7.827), (0.021, 0.056), (0.007, 0.035)),
    'tunicates':       (30,  (0.047, 0.052), (0.015, 0.010), (0.311, 0.278), (0.0003, 0.001), (None, None)),
    'echinoderms':     (20,  (0.009, 0.009), (0.022, 0.050), (0.782, 0.840), (0.0002, 0.001), (None, None)),
}

# S15  Zhang et al. 2017, Oncotarget (Honghu Lake, China) - Table 1, mg/kg wet wt,
#      mean ± SD per species; n per species from Table 6.
#      As values of 0.0000 are below detection recorded as zero (LOD not reported).
S15_GROUPS = {
    #                     n    As               Cd                Cr               Cu               Pb
    'bighead carp':       (8,  (0.0000, 0.0000), (0.0099, 0.0019), (0.6633, 0.0920), (0.1061, 0.0773), (0.0835, 0.0100)),
    'crucian carp':       (8,  (0.0000, 0.0000), (0.0087, 0.0049), (3.3600, 0.0036), (0.3829, 0.0786), (0.0938, 0.0004)),
    'grass carp':         (8,  (0.0000, 0.0000), (0.0032, 0.0002), (0.5369, 0.4395), (0.4502, 0.0726), (0.0111, 0.0111)),
    'mandarin fish':      (8,  (0.0000, 0.0000), (0.0066, 0.0004), (1.7000, 0.4952), (0.2398, 0.1716), (0.0639, 0.0232)),
    'small crucian carp': (16, (0.0000, 0.0000), (0.0072, 0.0032), (0.8760, 0.5790), (0.5171, 0.5157), (0.1536, 0.2661)),
    'yellow catfish':     (24, (0.0040, 0.0042), (0.0056, 0.0060), (0.3680, 0.1621), (1.9000, 1.2700), (0.1242, 0.0622)),
}

# Studies that report a single group directly (µg/kg wet weight).
DIRECT = {
    # S01  Wang et al. 2024, Environ Sci Eur - Table 1, "aquatic products" (carp), µg/kg,
    #      fresh weight after removal of inedible parts; n = 8 markets (Methods).
    'S01': dict(n=8, Pb=(165.4, 27.3), Cd=(35.7, 11.1), As=(880.4, 413.0), Cr=(207.4, 64.8), Cu=(268.0, 75.1)),
    # S02  Zhang et al. 2023, Toxics - abdominal muscle; dry-weight Table 1 values divided by the
    #      authors' own wet/dry factor 5.75 (Section 3.1).  The text states the resulting wet-weight
    #      means: Pb 23.2, Hg 86.9, Cd 0.8, As 121.1, Cu 2782.1 µg/kg.  SDs are the dry-weight SDs
    #      divided by 5.75.  n = 38 sampling sites (1,140 crayfish pooled within sites).
    'S02': dict(n=38, Pb=(23.2, 60 / 5.75), Cd=(0.8, 8 / 5.75), As=(121.1, 200 / 5.75), Hg=(86.9, 260 / 5.75),
                Cu=(2782.1, 12000 / 5.75)),
    # S10  Kosker et al. 2023, Front Nutr - Table 3, 34 canned products (mg/kg ww); mean and SD across
    #      products computed from the per-product means; NA entries dropped (see s10_parsed.json).
    'S10': None,      # filled from s10_parsed.json at run time
}

STUDY_LABEL = {
    'S01': 'Wang et al. 2024 (China; carp)',
    'S02': 'Zhang et al. 2023 (China; crayfish muscle)',
    'S10': 'Kosker et al. 2023 (Türkiye; canned fish)',
    'S11': 'Kim et al. 2023 (Korea; fish & shellfish)',
    'S15': 'Zhang et al. 2017 (China; lake fish)',
}
