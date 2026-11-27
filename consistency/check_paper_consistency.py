#!/usr/bin/env python3
"""Four-layer paper-vs-artifact consistency checker for the CSE 2026 paper.

Exit code 0 only when everything is green (usable as a commit gate).

  L1  table cells : Tables 2-5 of main.tex vs consistency/results_summary.json (tolerance 0.6 ulp of the
                    printed precision).  The number of compared cells is asserted, so a row whose key does
                    not match can never be skipped silently.
  L1b Table 1     : 7 category rows, 21 indicators, bold set = the four composites.
  L2  figures     : Fig. 1 (every indicator / category name of Table 1 appears in the TikZ source),
                    Fig. 2 (caption vs train_curves.csv), Fig. 3 (bar labels vs Table 5 means through the
                    plot manifest when one exists; otherwise reported as not machine-checked).
  L3  tripwires   : (label, exact LaTeX string) for every narrative number; the strings are regenerated
                    from the summary, never typed by hand.
  plus boolean claims (simplex invariants, H degeneracy, significance counts, ...).

Sources follow the reuse manual: raw recompute > derived CSV > md report (Table 4 and the three
supplementary experiments are md-sourced because their per-episode corpora are not shipped).
"""
import os, re, sys, json, argparse
from decimal import Decimal, ROUND_HALF_UP

ap = argparse.ArgumentParser()
HERE = os.path.dirname(os.path.abspath(__file__)); PAPER = os.path.dirname(HERE)
ap.add_argument('--paper', default=os.path.join(PAPER, 'main.tex'))
ap.add_argument('--summary', default=os.path.join(HERE, 'results_summary.json'))
_PARENT = os.path.dirname(HERE)   # inside the artifact (anon_repo_v2/consistency) the repo root is the parent directory
ap.add_argument('--repo', default=_PARENT if os.path.isdir(os.path.join(_PARENT, 'wxpgzs_src')) else os.path.join(PAPER, 'anon_repo_v2'))
ap.add_argument('--figdir', default=os.path.join(PAPER, 'figures'))
A = ap.parse_args()
S = json.load(open(A.summary, encoding='utf-8')); tex = open(A.paper, encoding='utf-8').read()
ok = {'L1': 0, 'L1b': 0, 'L2': 0, 'L3': 0}; fails = []; notes = []

def chk(layer, cond, msg):
    if cond: ok[layer] += 1
    else: fails.append((layer, msg)); print('  FAIL [%s] %s' % (layer, msg))
def fmt(x, d): return str(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))
def num(s): return float(s.replace('{,}', '').replace(',', '').replace('$', '').strip())
def close(pv, av, d): return abs(pv - av) <= 0.6 * 10 ** (-d) + 1e-12
def pm(cell):
    m = re.match(r'^\$?(-?[\d.]+)\s*\\pm\s*(-?[\d.]+)\$?$', cell.strip())
    return (num(m.group(1)), num(m.group(2))) if m else None
def table_block(label):
    i = tex.find('\\label{%s}' % label); return tex[tex.rfind('\\begin{table}', 0, i):tex.find('\\end{table}', i)]
def cells(row):
    row = re.sub(r'\\(?:top|mid|bottom)rule', '', row)
    return [c.strip() for c in row.strip().split('&')]
def rows_of(blk): return [r for r in blk.split('\\\\') if '&' in r]
def rng(vals, d): return (fmt(min(vals), d), fmt(max(vals), d))
def mean(v): return sum(v) / len(v)

T3 = S['t3']['cells']; T5 = S['t5']['units']; T4 = S['t4']['units']; N = S['narrative']; E = S['_c4eps']
LEARNED = ['GNN-PPO', 'GNN-PPO-det', 'H-MARL', 'H-MARL-det']
CONTRACTOR = ['RL baseline (B-line)', 'RL baseline (Meander)', 'RL baseline (R.-Select)']
v9 = open(os.path.join(A.repo, 'report/phase5_report_cn_v9.md'), encoding='utf-8').read()

# ------------------------------------------------------------------ L1: Table 3
print('L1 Table 3 (Cyberwheel RL evaluation)')
arm = None; n = 0
for row in rows_of(table_block('tab:results'))[1:]:
    c = cells(row)
    if len(c) < 6: continue
    m = re.match(r'\\multirow\{6\}\{\*\}\{(\w+)\}', c[0])
    if m: arm = m.group(1)
    key = '%s|%shost|%s' % (arm, c[1].strip(), '1' if c[2].strip() == 'on' else '0')
    if key not in T3: chk('L1', False, 'Table 3 row key not in artifact truth: %s' % key); continue
    for col, cell in zip(('Node Ctrl.', 'Detect', 'Damage'), c[3:6]):
        p = pm(cell)
        if not p: chk('L1', False, 'Table 3 %s %s: unparsable cell %s' % (key, col, cell)); continue
        for which, pv in zip(('mean', 'sd'), p):
            n += 1; av = T3[key][col][which]
            chk('L1', close(pv, av, 3), 'Table 3 %s %s %s: paper %s vs artifact %.5f' % (key, col, which, pv, av))
chk('L1', n == 108, 'Table 3: compared %d numbers, expected 108' % n)
chk('L1', S['t3']['md_crosscheck']['n'] == 9 and S['t3']['md_crosscheck']['max_abs_diff'] <= 1e-4,
    'Table 3 recompute does not reproduce the nine v9 section-3.1 cells (max diff %.5f)' % S['t3']['md_crosscheck']['max_abs_diff'])
print('  numbers compared: %d (expected 108) | md cross-check: %d cells, max diff %.5f' % (n, S['t3']['md_crosscheck']['n'], S['t3']['md_crosscheck']['max_abs_diff']))

# ------------------------------------------------------------------ L1: Table 5
print('L1 Table 5 (CAGE4 final-step indicators)')
n = 0; seen = []
for row in rows_of(table_block('tab:cage4')):
    c = cells(row); name = c[0]
    if name not in T5: continue
    u = T5[name]; seen.append(name)
    if len(c) == 7:
        n += 1; chk('L1', abs(num(c[1]) - u['steps']) < 1e-9, 'Table 5 %s steps: paper %s vs artifact %d' % (name, c[1], u['steps']))
        for col, cell in zip(('node_control_rate', 'subnet_control_rate', 'node_failure_rate', 'd_score'), c[2:6]):
            for which, pv in zip(('mean', 'sd'), pm(cell)):
                n += 1; chk('L1', close(pv, u[col][which], 3), 'Table 5 %s %s %s: paper %s vs artifact %.5f' % (name, col, which, pv, u[col][which]))
        for which, pv in zip(('mean', 'sd'), pm(c[6])):
            n += 1; chk('L1', close(pv, u['lateral_movement_ratio'][which], 1), 'Table 5 %s Lat.-Mov. %s: paper %s vs artifact %.4f' % (name, which, pv, u['lateral_movement_ratio'][which]))
    elif len(c) == 6:
        for col, cell in zip(('dc_score', 'di_score', 'da_score', 'd_score', 'comprehensive_concealment_score'), c[1:6]):
            for which, pv in zip(('mean', 'sd'), pm(cell)):
                n += 1; chk('L1', close(pv, u[col][which], 3), 'Table 5 %s %s %s: paper %s vs artifact %.5f' % (name, col, which, pv, u[col][which]))
chk('L1', sorted(set(seen)) == sorted(T5) and len(seen) == 14, 'Table 5 rows matched: %s' % seen)
chk('L1', n == 147, 'Table 5: compared %d numbers, expected 147' % n)
print('  rows matched: %d (expected 14) | numbers compared: %d (expected 147)' % (len(seen), n))

# ------------------------------------------------------------------ L1: Table 4 (md source)
print('L1 Table 4 (Cyberwheel training / long-horizon units, md report source)')
n = 0; seen = []
for row in rows_of(table_block('tab:cwtrain')):
    c = cells(row); unit = c[0].split(' ')[0]
    if unit not in T4: continue
    t = T4[unit]; nums = t['_nums']; seen.append(unit); n += 2
    chk('L1', int(num(c[1])) == t['episodes'], 'Table 4 %s episodes: paper %s vs md %d' % (unit, c[1], t['episodes']))
    chk('L1', int(num(c[2])) == int(fmt(t['steps'], 0)), 'Table 4 %s steps: paper %s vs md %.1f' % (unit, c[2], t['steps']))
    for col, cell, idx in (('Damage', c[3], 0), ('Node Ctrl.', c[4], 4), ('Detect', c[5], 5), ('Conceal.', c[6], 6)):
        mv, sv = nums[idx]; p = pm(cell); n += 2
        chk('L1', p is not None and close(p[0], mv, 3), 'Table 4 %s %s mean: paper %s vs md %s' % (unit, col, cell, mv))
        chk('L1', p is not None and ((sv is None and p[1] == 0.0) or (sv is not None and close(p[1], sv, 3))), 'Table 4 %s %s std: paper %s vs md %s' % (unit, col, cell, sv))
chk('L1', sorted(set(seen)) == sorted(T4) and len(seen) == 12, 'Table 4 rows matched: %d' % len(seen))
chk('L1', n == 120, 'Table 4: compared %d numbers, expected 120' % n)
print('  rows matched: %d (expected 12) | numbers compared: %d (expected 120)' % (len(seen), n))

# ------------------------------------------------------------------ L1: Table 2
print('L1 Table 2 (configuration counts)')
rt = sum(T4[u]['episodes'] for u in T4 if u.startswith('CW-RT')); at = sum(T4[u]['episodes'] for u in T4 if u.startswith('CW-AT'))
xrt = sum(T4[u]['episodes'] for u in T4 if u.startswith('CWX-RT')); xat = sum(T4[u]['episodes'] for u in T4 if u.startswith('CWX-AT'))
t2 = N['t2']; matched = 0
EXPECT = {('CW eval (RL / scripted)', -1): '%d / %d' % (t2['cw_eval_rl'], t2['cw_eval_art']), ('CW train / long', -1): '%d/%d (train); %d/%d (long)' % (rt, at, xrt, xat),
          ('CW sampled', -1): '%d' % t2['cw_sampled'], ('CW variants', -1): '%d' % t2['cw_variants'], ('CAGE4', -1): '%d' % t2['cage4'],
          ('CW eval (RL / scripted)', 1): '10/25/50 h', ('CW variants', 4): '10{,}000 steps', ('CAGE4', 1): '%d--%d h' % tuple(N['cage4_hosts'])}
for row in rows_of(table_block('tab:setup')):
    c = cells(row)
    for (k0, idx), exp in EXPECT.items():
        if c[0].startswith(k0):
            matched += 1; chk('L1', c[idx] == exp, 'Table 2 %s cell %d: paper %s vs expected %s' % (k0, idx, c[idx], exp))
chk('L1', matched == len(EXPECT), 'Table 2 cells matched: %d, expected %d' % (matched, len(EXPECT)))
print('  cells matched: %d (expected %d)' % (matched, len(EXPECT)))

# ------------------------------------------------------------------ L1b: Table 1
print('L1b Table 1 (indicator system)')
blk = tex[tex.find('\\label{tab:indicators}'):]; blk = blk[:blk.find('\\end{tabular}')]
t1 = [cells(r) for r in blk.split('\\\\') if '&' in r and 'Dimension (Eq.)' not in r]
names = [x.strip() for r in t1 if len(r) >= 3 for x in re.split(r';|,', re.sub(r'\\textbf\{([^}]*)\}', r'\1', r[2])) if x.strip()]
bold = set(re.findall(r'\\textbf\{([^}]*)\}', blk)) - {'Dimension (Eq.)', 'Category', 'Indicators'}
cats = [r[1] for r in t1 if len(r) >= 3]
chk('L1b', len(cats) == 7, 'Table 1 category rows: %d (expected 7)' % len(cats))
chk('L1b', len(names) == 21 and len(set(names)) == 21, 'Table 1 indicators: %d distinct %d (expected 21)' % (len(names), len(set(names))))
chk('L1b', bold == {'Comprehensive Detection Rate', 'Control Scope', 'Comprehensive Concealment', 'Comprehensive Damage'}, 'Table 1 bold set: %s' % sorted(bold))
print('  rows %d | indicators %d | bold %d' % (len(cats), len(names), len(bold)))

# ------------------------------------------------------------------ L2: figures
print('L2 figures')
def norm(s): return re.sub(r'\s+', ' ', s.replace('\\\\', ' ').replace('~', ' ').replace('\\%', '%')).strip().lower()
tikz = norm(open(os.path.join(A.figdir, 'fig_hierarchy.tex'), encoding='utf-8').read())
ALIAS = {'Comprehensive Concealment': 'Concealment\\\\Composite $H$', 'Comprehensive Damage': 'Damage\\\\Composite $D$'}
miss = [x for x in names + cats if norm(ALIAS.get(x, x)) not in tikz]
chk('L2', not miss, 'Fig. 1 TikZ source is missing Table-1 names: %s' % miss)
f2 = N['fig2']
chk('L2', all(v == 22 for v in f2['A_first_zero'].values()), 'Fig. 2: arm-A first zero-deployment episode per scale %s (caption says by episode 22)' % f2['A_first_zero'])
chk('L2', f2['A_deploys_ep14_21_max']['25host'] <= 5, 'Fig. 2 (25-host panel): arm-A deploys in episodes 14-21 reach %.1f per episode' % f2['A_deploys_ep14_21_max']['25host'])
chk('L2', f2['A_hits_max'] == 0, 'Fig. 2: arm-A training decoy hits are not all zero')
man_path = os.path.join(HERE, 'fig_cage4_overview.manifest.json')
if os.path.exists(man_path):
    man = json.load(open(man_path))
    for name, v in man['left_labels'].items(): chk('L2', abs(float(v) - T5[name]['d_score']['mean']) <= 6e-4, 'Fig. 3 label %s: %s vs %.4f' % (name, v, T5[name]['d_score']['mean']))
    for name, comp in man['right_components'].items():
        for col, v in comp.items(): chk('L2', abs(v - T5[name][col]['mean']) <= 6e-4, 'Fig. 3 %s %s: %s vs %.4f' % (name, col, v, T5[name][col]['mean']))
else:
    notes.append('Fig. 3: no plot manifest; bar labels are checked by vision against Table 5 (see audit log), not by this script')

# ------------------------------------------------------------------ L3: tripwires
print('L3 narrative tripwires')
trip = []
def T(label, s): trip.append((label, s))
def cut(): return rng(list(N['cut_pct'].values()), 0)
T('episodes total', 'more than 1{,}300 attack episodes'); T('indicator count', '7 categories and 21 indicators')
T('abstract D learned', '($D = %s$--$%s$)' % rng([T5[x]['d_score']['mean'] for x in LEARNED], 2))
T('abstract D contractor', '($D = %s$--$%s$; about $10\\times$ under a common horizon)' % rng([T5[x]['d_score']['mean'] for x in CONTRACTOR], 3))
sb1 = rng(list(N['strike_b1'].values()), 1); sb2 = rng(list(N['strike_b2'].values()), 1)
T('abstract strike B1', '$%s$--$%s\\%%$ of core attacks' % sb1); T('abstract strike B2', 'cuts this to $%s$--$%s\\%%$' % sb2)
T('abstract paired', 'red-agent damage is $%s$--$%s\\%%$ lower in 45/45 paired sampled-action episodes' % rng([N['paired']['GNN'], N['paired']['HMARL']], 0))
T('episodes per cell', '45 episodes per cell, 810 in total'); T('cross-arm episodes', 'under sync-on (45 episodes)')
T('ART episodes', '15 episodes per scale'); T('B1 train episodes', '300 arm-B1 episodes'); T('ART train episodes', '50 ART-defender episodes')
W = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six'}
T('subnets', 'across %s to %s subnets' % (W[min(N['cw_subnets'].values())], W[max(N['cw_subnets'].values())]))
_w = {9: 'nine', 8: 'eight', 10: 'ten'}.get(N['cage4_subnets'][0], str(N['cage4_subnets'][0]))
T('CAGE4 hosts', 'network of %d--%d hosts across %s subnets' % (tuple(N['cage4_hosts']) + (_w,)))
chk('L3', N['cage4_topologies'] == 21 and N['cage4_subnets'] == [9], 'CAGE4 sidecars: %d topologies, subnet counts %s' % (N['cage4_topologies'], N['cage4_subnets']))
T('CAGE4 episodes', 'evaluate 21 episodes from CAGE Challenge 4')
T('grid', '231 admissible weightings'); T('gap', 'minimum between-group gap $%s$' % fmt(N['simplex_cage4']['min_gap'], 2)); T('tau', 'Kendall $\\tau \\geq %s$' % fmt(N['simplex_cage4']['min_tau'], 2))
T('box', 'within $[0.15, 0.55]$'); T('flip', 'availability share $\\geq 0.6$'); T('H degenerate', '$H = 1.0$ under every weighting')
fl = N['flag']
T('flag ART', 'is $%d\\%%$ for Cyberwheel ART' % int(fmt(fl['cw_art_eval'], 0)))
T('flag CAGE4 contractor', '$%s$--$%s\\%%$ for the CAGE4 contractor episodes with scripted red' % rng(fl['cage4_contractor'], 0))
T('flag CW RL', 'about $%s\\%%$ for Cyberwheel RL' % fmt(fl['cw_rl_eval'], 1))
T('flag CAGE4 learned', '$%s$--$%s\\%%$ for the CAGE4 learned-defender episodes' % rng(fl['cage4_learned'], 0))
sp = S['_spearman']; rho = sp['rho']
T('spearman recipe', 'all 810 episodes of the 54 arm--scale--seed--sync configurations')
T('spearman median', 'median Spearman $\\rho = %s$ over the %d recomputable indicators' % (fmt(sp['median'], 2), sp['n_defined']))
T('spearman composites', '$\\rho = %s$ for the concealment composite, $%s$ for $D$' % (fmt(rho['comprehensive_concealment_score'], 2), fmt(rho['d_score'], 2)))
T('spearman sensitive', '$\\rho = %s$ for node control, $%s$ for control value and integrity damage, $-%s$ for total control time' % (fmt(rho['node_control_rate'], 2), fmt(rho['control_value'], 2), fmt(abs(rho['total_control_time']), 2)))
IC = ('node_alive_detection_rate', 'node_info_detection_rate', 'node_vulnerability_detection_rate', 'node_detect_rate')   # the four Information Collection indicators of Table 1
T('spearman information collection', r'and so are the Information Collection detection rates ($\rho \geq %s$)' % fmt(min(rho[k] for k in IC), 2))
chk('L3', all(rho[k] >= 0.6 for k in IC) and abs(rho['di_score'] - rho['control_value']) < 1e-9, 'rank-sensitivity wording facts: Information Collection min rho %.3f / DI %.3f vs control value %.3f' % (min(rho[k] for k in IC), rho['di_score'], rho['control_value']))
T('flag denominator', '(share of red actions except sleep and subnet scans flagged successful)')
T('spearman conclusion', r'so all-action counting changes individual readings but leaves the damage-based patterns of Table~\ref{tab:results} intact: the 25-host peak everywhere and the arm ordering $B1 < A < B2$ at 50 hosts.')
T('spearman recipe wording', r'), recomputed with the shipped pipeline from successful actions only, yields')
T('weighting conclusion placement', r'under every weighting. The separations at issue are therefore not artifacts of the weighting choice. \emph{Action semantics}')
ptn = N['patterns']
chk('L3', ptn['all_action']['peak25']['d_score'] and ptn['success_only']['peak25']['d_score'] and ptn['success_only']['b1_lt_a_lt_b2_50h']['d_score'], 'patterns claimed as intact under success-only counting do not hold: %s' % ptn)
chk('L3', not ptn['success_only']['b2_gt_b1']['d_score'] and not ptn['success_only']['peak25']['node_control_rate'], 'success-only patterns changed (B2>B1 or the node-control peak now holds): re-read the Spearman sentence')
T('peak', 'peaks at the 25-host topology')
b1r = rng([T3['B1|50host|%d' % y]['Damage']['mean'] for y in (0, 1)], 3); b2r = rng([T3['B2|50host|%d' % y]['Damage']['mean'] for y in (0, 1)], 3)
T('B1 50h D', '($D = %s$--$%s$)' % b1r); T('B2 50h D', 'sustains $D = %s$--$%s$' % b2r)
ae = N['art_eval']
T('ART eval', '$D = %s \\pm %s$ at 25 hosts (node control $%s$), versus $%s$ at 10 and $%s$ at 50 hosts' % (fmt(ae['25'], 3), fmt(ae['25_sd'], 3), fmt(ae['ctrl25'], 3), fmt(ae['10'], 3), fmt(ae['50'], 3)))
T('ART loops', '$%s\\%%$ of ART' % fmt(N['art_loops_pct'], 1))
dep = N['deploy_per_ep_sync_on']; T('deploy per episode', '(%s--%s per episode)' % (fmt(min(dep), 0), fmt(max(dep), 0)))
T('strike B1 text', '$%s$--$%s\\%%$ of core attacks (exploitation, lateral movement, privilege escalation, impact) under B1, dropping to $%s$--$%s\\%%$ under B2' % (sb1 + sb2))
so = N['sync_off_A']
T('sync-off A', 'Across all %d sync-off arm-A episodes the defender deploys zero decoys' % so['episodes'])
chk('L3', so['episodes'] == 3 * 45 and so['decoy_records'] == 0, 'sync-off arm-A episodes / decoy records from the manifests: %s' % so)
ca = N['crossarm']
T('cross-arm ranges', 'column range up to $%s$ in $D$ vs.\\ row range $%s$' % (fmt(ca['col_range_red'], 3), fmt(ca['row_range_blue'], 3)))
T('cross-arm diag', '$D = %s$ off-diagonal vs.\\ $%s$ on' % (fmt(ca['offdiag'], 3), fmt(ca['diag'], 3)))
T('train D', '$D = %s$, $%s$, $%s$ across scales' % tuple(T4['CW-RT%shost' % h]['_md3']['D'] for h in (10, 25, 50)))
T('long D', 'reaches $D = %s$ with full node control' % fmt(T4['CWX-RT25host']['_nums'][0][0], 3))
T('stepsens design', '72 paired rollouts at 100/500/1{,}000 steps'); T('stepsens positive', '%d/36 paired cells' % N['stepsens']['n_pos'])
T('conceal collapse', '$%s \\to %s$' % (fmt(T4['CW-AT25host']['_nums'][6][0], 3), fmt(T4['CWX-AT25host']['_nums'][6][0], 3)))
a1000 = N['stepsens']['arms1000']; T('stepsens convergence', 'within $%s$ in $D$ at 50 hosts' % fmt(max(a1000) - min(a1000), 3))
T('collapse episodes', 'by episodes 14--22'); T('fig2 caption', 'abandons deployment by episodes 14--22')
T('CAGE4 D learned', '$D = %s$--$%s$, node control up to $%s$' % (rng([T5[x]['d_score']['mean'] for x in LEARNED], 3) + (fmt(max(T5[x]['node_control_rate']['mean'] for x in LEARNED), 3),)))
T('CAGE4 D contractor', 'hold the red agent to $D = %s$--$%s$' % rng([T5[x]['d_score']['mean'] for x in CONTRACTOR], 3))
T('steps contractor', 'terminate in $%d$--$%d$ steps' % (min(T5[x]['steps'] for x in CONTRACTOR), max(T5[x]['steps'] for x in CONTRACTOR)))
T('steps learned', 'sustain $%d$--$%d$' % (min(T5[x]['steps'] for x in LEARNED), max(T5[x]['steps'] for x in LEARNED)))
d80l = [mean(E[x]['d80']) for x in LEARNED]; d80c = [mean(E[x]['d80']) for x in CONTRACTOR]
T('80-step', '$D = %s$--$%s$ versus $%s$--$%s$' % (rng(d80l, 2) + rng(d80c, 3))); T('10x', '$\\approx 10\\times$')
T('DC range', '$DC = %s$--$%s$' % rng([T5[x]['dc_score']['mean'] for x in LEARNED], 3)); T('DA range', '$DA = %s$--$%s$' % rng([T5[x]['da_score']['mean'] for x in LEARNED], 3))
T('decoys', '${\\sim}%d$ decoy hosts' % int(fmt(mean(N['decoys_per_ep']['GNN-PPO']), 0)))
P = N['paired']
T('absorb', '$%s\\%%$ to $%s\\%%$ of attack steps land on decoys' % (fmt(float(P['absorb_lo']), 1), fmt(float(P['absorb_hi']), 1)))
T('conceal per-episode', '$%s$--$%s$ across episodes' % rng([e['comprehensive_concealment_score'] for x in LEARNED for e in E[x]['eps']], 3))
T('paired pct', '$%s\\%%$ (GNN-PPO) and $%s\\%%$ (H-MARL)' % (fmt(P['GNN'], 1), fmt(P['HMARL'], 1)))
T('paired consistent', 'consistent in 45/45 episode pairs per variant'); T('resamples', '20{,}000 resamples'); T('p', '$p < 0.001$')
def psig(p): return '$p < 0.001$' if p < 0.001 else '$p < 0.01$' if p < 0.01 else '$p < 0.05$' if p < 0.05 else 'not significant'
T('det effects', 'under deterministic policies the effect attenuates ($%s\\%%$ for H-MARL-det, $%d/%d$ consistent, %s; $%s\\%%$ for GNN-PPO-det, %s)' % (fmt(P['HMARL-Det']['pct'], 1), P['HMARL-Det']['consistent'], P['HMARL-Det']['n'], psig(P['HMARL-Det']['p_holm']), fmt(P['GNN-Det']['pct'], 1), psig(P['GNN-Det']['p_holm'])))
T('abstract det variants', '(deterministic variants: $%s\\%%$ and $%s\\%%$)' % (fmt(P['HMARL-Det']['pct'], 1), fmt(P['GNN-Det']['pct'], 1)))
T('det decoys', 'GNN-PPO-det deploys roughly six times fewer decoys than its sampled counterpart ($%s$ vs.\\ $%s$ per episode)' % tuple(P['decoy_det_per_ep']))
chk('L3', 5.5 <= float(P['decoy_det_per_ep'][1]) / float(P['decoy_det_per_ep'][0]) < 6.5, 'paired experiment decoy ratio is not about six: %s' % P['decoy_det_per_ep'])
T('decoys paired', '$%s$ vs.\\ $%s$ per episode' % tuple(P['decoy_det_per_ep']))
sr = N['same_red']; srl = rng(sr['learned'], 3); src = rng(sr['contractor'], 3)
T('same-red rollouts', '(%d rollouts,' % sr['rollouts']); T('same-red text', 'to $%s$--$%s$, while the heavily deploying GNN-PPO/H-MARL variants accept $%s$--$%s$' % (src + srl)); T('same-red price', '($%s$--$%s$ vs.\\ $%s$--$%s$)' % (srl + src))
T('cut+damage', 'the $%s$--$%s\\%%$ engagement cut at sustained real-host damage ($%s$--$%s$ vs.\\ $%s$--$%s$ at 50 hosts)' % (cut() + b2r + b1r))
off = N['official']
def _k(x): return format(round(abs(x)), ',').replace(',', '{,}')
T('official', '$-%s$/$-%s$ for GNN-PPO/H-MARL, $-%s$/$-%s$' % (round(abs(off['GNN-PPO'])), _k(off['H-MARL']), _k(off['GNN-PPO-det']), _k(off['H-MARL-det'])))
T('scalar cannot surface', 'a divergence the scalar score itself does not show.'); T('score naming', "The challenge's blue-reward score and the damage-oriented indicator profile")
T('point estimates', '($%s$ vs.\\ $%s$, $%s$ vs.\\ $%s$)' % tuple(fmt(T5[x]['d_score']['mean'], 3) for x in ('GNN-PPO', 'H-MARL', 'GNN-PPO-det', 'H-MARL-det')))
fc = [x for xname in LEARNED + CONTRACTOR for x in E[xname]['first_compromise'] if x is not None]
T('first compromise', '$%d$--$%d$ steps' % (min(fc), max(fc)))
samp = ['GNN-PPO', 'H-MARL']; detv = ['GNN-PPO-det', 'H-MARL-det']
T('conceal gap', '($%s$--$%s$ vs.\\ $%s$--$%s$)' % (rng([T5[x]['comprehensive_concealment_score']['mean'] for x in samp], 2) + rng([T5[x]['comprehensive_concealment_score']['mean'] for x in detv], 2)))
T('paired lower', 'damage $%s$--$%s\\%%$ lower with decoys on' % rng([P['GNN'], P['HMARL']], 0))
T('further cut', '(a further $%s$--$%s\\%%$ cut, with a significant shift toward real hosts on two of three topologies)' % cut())
T('cross-arm strike', 'carry their strike rates across blue partners (share of all logged steps, five episodes per pair: red-B1 $%s$--$%s\\%%$; red-A $%s\\%%$' % (fmt(ca['strike_b1_range'][0] * 100, 1), fmt(ca['strike_b1_range'][1] * 100, 1), fmt(ca['strike_max']['A'] * 100, 1)))
T('kill chain', 'projecting the kill-chain stages of Hutchins et al.')
T('distinct quantities', 'only the first duplicates a quantity, so the system covers 20 distinct quantities')
T('supplementary corpora', 'A sampled-action variant of the arm-A red agent adds five episodes.'); T('ART variants', 'in ten script variants, against arm~B1.')
T('antecedent', 'Both the spread and the horizon gap are reward-shaped: early termination under presence-minimizing rewards, long engagement tolerance under service-continuity rewards')
# audit 48: the visible LNCS template settings must stay restored (class caption style, no page enlargement, no old-class incompatibility)
for _bad in ('\\usepackage{caption}', '\\captionsetup', '\\usepackage{subcaption}', '\\enlargethispage'):
    chk('L3', _bad not in tex, 'template deviation re-introduced: %r (llncsdoc 2.1: caption style and printing area are set by the class)' % _bad)
chk('L3', tex.count('\\@ifundefined{credits}') == 1 and tex.index('\\@ifundefined{credits}') < tex.index('\\begin{document}'), 'llncs.cls < v2.23 compatibility block missing from the preamble')
chk('L3', re.search(r'\\documentclass\[runningheads,a4paper\]\{llncs\}', tex) is not None, 'documentclass line must read \\documentclass[runningheads,a4paper]{llncs} (CSE 2026 template note)')
T('peak wording', 'falls below it at 50 hosts')
T('limitation term', r'the all-action versus success-only comparison is run only on the Cyberwheel corpus')
# audit 49: the author removed all section cross-references as redundant (2026-11-25); do not let them creep back
chk('L3', not re.search(r'\\ref\{sec:', tex) and not re.search(r'(?<![A-Za-z{])Sections?~?\s*\d+(\.\d+)?\b', re.sub(r'(?<!\\)%.*$', '', tex, flags=re.M)), 'section cross-references re-introduced (author removed them as redundant)')
T('dependencies', 'needs only the standard library plus PyYAML (Matplotlib only for the optional charts) and is deterministic')
_wsrc = os.path.join(A.repo, 'wxpgzs_src'); _std = set(sys.stdlib_module_names); _top = set(); _opt = set()
_local = {os.path.splitext(f)[0] for f in os.listdir(_wsrc) if f.endswith('.py')}
for _fn in sorted(f for f in os.listdir(_wsrc) if f.endswith('.py')):
    for _l in open(os.path.join(_wsrc, _fn), encoding='utf-8'):
        _m = re.match(r'^(\s*)(?:import|from)\s+([A-Za-z_]\w*)', _l)
        if _m: (_opt if _m.group(1) else _top).add(_m.group(2))
_third_top = {x for x in _top if x not in _std and x not in _local}; _third_opt = {x for x in _opt if x not in _std and x not in _local}
chk('L3', _third_top == {'yaml'} and _third_opt <= {'yaml', 'matplotlib', 'numpy'}, 'dependency claim (standard library + PyYAML; Matplotlib for charts) no longer matches the pipeline imports: %s / %s' % (_third_top, _third_opt))
for _bad in ('no significant effect', 'core actions flagged', 'robust to small weight perturbations', '7-kill-chain', 'confirmed-metric dual reading', 'stops deploying decoys entirely', 'Both components are reward-shaped', 'drops at 50 hosts', 'preserves the comparative orderings', 'inflates individual readings', 'uses only the Python standard library', 'control- and value-type indicators are convention-sensitive', 'minimal disruption', 'distinct strike profiles everywhere', 'redirected toward real hosts', 'is a short Python program', 'decoy-strike share', 'realized impairment', 'do not depend on the weighting choice', 'no scalar score can surface', 'The official score', 'every red checkpoint with every blue checkpoint', 'byte-identical to its 1,000-step prefix', '$H = 1.000$ under'):
    chk('L3', _bad not in tex, 'stale wording still present: %r' % _bad)
for _bad in ('92--101',):
    chk('L3', _bad not in tex, 'stale wording still present: %r' % _bad)
# reachability of the Data Availability link (informational only: network dependent, never fails the run)
_m = re.search(r'\\url\{(https://github\.com/[^}]+)\}', tex)
if _m:
    try:
        import urllib.request
        _code = urllib.request.urlopen(urllib.request.Request(_m.group(1), headers={'User-Agent': 'consistency-check'}), timeout=20).status
    except Exception as _e:
        _code = getattr(_e, 'code', str(_e))
    notes.append('Data Availability URL %s answers HTTP %s (200 expected once the repository is public)' % (_m.group(1), _code))
T('contractor objective (abstract)', 'than those optimized for minimal attacker presence ($D = 0.018$--$0.049$')
T('contractor objective (conclusion)', 'than those optimized for minimal attacker presence, and')
T('contractor objective (5.3)', 'early termination under presence-minimizing rewards, long engagement tolerance under service-continuity rewards')
T('contractor objective (intro)', 'aggressive decoy deployment under one reward, minimal attacker presence under another')
T('sync-on deployment arms', 'Under sync-on, the connected arms B1/B2 deploy decoys')
T('ART attribution', 'Its decoy engagement, moreover, demands careful attribution')
T('CIA wording', 'The three CIA components each track impairment-related activity, but')
T('weighting claim (4.1)', 'the configuration separations are robust to the weighting choice')
T('H precision', 'sit at the degenerate $H = 1.0$ under every weighting.')
T('Eq. 2 cardinalities', r'\chi_d = \frac{|O_d|}{N_d}'); T('control range names', r'where the horizontal control range $s_h$ is'); T('Table 5 header', r'\textbf{Node Failure} & \textbf{Damage}')
T('CIA expanded', 'the three CIA (confidentiality, integrity, availability) damage components')
T('cross-arm design', 'pairs the seed-1 red checkpoints with the seed-1 blue checkpoints of all arms')
_asi = N['art_sync_identity']; _n = len(_asi); _k = sum(1 for r in _asi if str(r.get('identical')) == 'True')
T('ART sync identity', 'byte-identical under both synchronization states in %d of %d episode pairs' % (_k, _n))
chk('L3', _n == 15, 'ART sync-identity table has %d rows, expected 15' % _n)
T('long-horizon wording', 'each 10,000-step ART episode replays the 1,000-step script (on five episodes per scale)')
T('paired sample', 'beyond the three episodes of Table~\\ref{tab:cage4}; sign-flip permutation test')
_ns = sum(1 for p in N['redirect_p_real'].values() if p < 0.05)
chk('L3', _ns == 2, 'redirection is significant on %d of three topologies, wording says two' % _ns)
missing = [(l, s) for l, s in trip if s not in tex]
for l, s in missing: chk('L3', False, 'tripwire "%s" not found: %s' % (l, s))
ok['L3'] += len(trip) - len(missing)
print('  registered %d | present %d | missing %d' % (len(trip), len(trip) - len(missing), len(missing)))

# ------------------------------------------------------------------ boolean claims
sc = N['simplex_cw']; sc4 = N['simplex_cage4']
chk('L3', sc['box_points'] == 60 and sc['box_violations'] == 0 and sc['pm01_b2b1_peak_hold'], 'Cyberwheel simplex: B2>B1 and 25-host peak do not hold on the whole box (%s)' % sc)
chk('L3', sc['violators_all_wA_ge_06'] and sc['violators_only_C_or_I_ge_06'] == 0, 'Cyberwheel simplex: some violating weighting has availability share < 0.6')
chk('L3', sc4['points'] == 231 and sc4['min_gap'] > 0 and sc4['min_tau'] >= 0.425, 'CAGE4 simplex separation not invariant (%s)' % sc4)
hc = N['h_cells']
chk('L3', all(v['conceal'] < 1.0 for k, v in hc.items() if not k.startswith('A|')) and all(v['conceal'] == 1.0 for k, v in hc.items() if k.startswith('A|')), 'H: non-arm-A cells must be < 1.0 and arm-A cells = 1.0 at the default weighting')
chk('L3', all(v['Hb'] < 1.0 for k, v in hc.items() if not k.startswith('A|')), 'H: a decoy-deploying cell has behavior concealment = 1.0 (strictness claim fails)')
chk('L3', sum(1 for p in N['redirect_p_real'].values() if p < 0.05) == 2, 'redirection significance must hold on exactly two of three topologies')
chk('L3', ca['armA_deploys_all'] and ca['n'] == 45, 'cross-arm: arm-A defender must deploy zero decoys in all 45 episodes')
chk('L3', N['stepsens']['n_pos'] == 36 and (max(a1000) - min(a1000)) <= 0.004 + 1e-12, 'step-sensitivity: %s / convergence %s' % (N['stepsens']['n_pos'], a1000))
chk('L3', (t2['cw_eval_rl'] + t2['cw_eval_art'] + rt + at + xrt + xat + t2['cw_sampled'] + t2['cw_variants'] + t2['cage4']) >= 1300, 'episode total below 1,300')
chk('L3', t2['cw_eval_rl'] == 810 and t2['cw_eval_art'] == 45 and t2['cw_sampled'] == 5 and t2['cw_variants'] == 10 and t2['cage4'] == 21, 'corpus counts: %s' % t2)
chk('L3', len(sp['undefined']) == 1 and sp['undefined'][0] == 'subnet_failure_rate' and sp['n_defined'] == 20, 'Spearman: undefined set %s' % sp['undefined'])
chk('L3', rho['total_control_time'] > -0.5, 'Spearman: total control time convention-sensitive again (%.3f)' % rho['total_control_time'])
chk('L3', P['HMARL-Det']['consistent'] < 45 and P['GNN-Det']['p_holm'] > 0.05 and P['HMARL-Det']['p_holm'] < 0.05, 'paired experiment consistency counts: %s' % P)
chk('L3', min(x['steps'] for x in T5.values()) <= 499, 'CAGE4 horizon claim (<= 499 steps)')

print()
for x in notes: print('NOTE: ' + x)
print('SUMMARY: L1 %d ok | L1b %d ok | L2 %d ok | L3 %d ok | failures: %d' % (ok['L1'], ok['L1b'], ok['L2'], ok['L3'], len(fails)))
print('ALL GREEN' if not fails else 'RED')
sys.exit(0 if not fails else 1)
