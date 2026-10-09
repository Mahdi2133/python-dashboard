"""Parse Kosker et al. 2023 Table 3 (34 canned fish products, mg/kg ww) from raw pdftotext output."""
import re, sys, statistics as st, json
raw = open(sys.argv[1], encoding='utf-8').read()
start = raw.index('TABLE 3 Metal levels in 34 canned')
seg = raw[start:start + 20000]
toks = seg.replace('\n', ' ').split()
# product codes look like P-1, D12, SF1, ...
cols = ['Fe', 'Cu', 'Zn', 'Se', 'Al', 'Cr', 'Pb', 'Cd', 'As']
prod_re = re.compile(r'^(P-\d+|[A-Z]{1,3}\d+)$')
rows = {}
i = 0
while i < len(toks):
    t = toks[i]
    if prod_re.match(t) and t not in rows and not t.startswith('TABLE'):
        vals, j = [], i + 1
        while len(vals) < 9 and j < len(toks):
            if toks[j] == 'NA':
                vals.append(None); j += 1; continue
            m = re.match(r'^\d+(\.\d+)?$', toks[j])
            if m and j + 2 < len(toks) and toks[j + 1] == '±':
                vals.append(float(toks[j])); j += 3; continue
            if m and toks[j - 1] not in ('±',):           # number without ± (rare)
                if toks[j + 1:j + 2] == ['±']:
                    pass
            j += 1
        if len(vals) == 9:
            rows[t] = vals
        i = j
        continue
    i += 1
print('products parsed:', len(rows))
out = {}
for k, c in enumerate(cols):
    xs = [v[k] for v in rows.values() if v[k] is not None]
    out[c] = dict(n=len(xs), mean=round(st.mean(xs), 4), sd=round(st.stdev(xs), 4), min=min(xs), max=max(xs))
    print('%-3s n=%2d mean=%8.4f sd=%8.4f range=%s-%s' % (c, len(xs), st.mean(xs), st.stdev(xs), min(xs), max(xs)))
json.dump(dict(rows=rows, summary=out), open('s10_parsed.json', 'w'), indent=1)
