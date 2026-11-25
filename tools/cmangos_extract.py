"""Extrait de la base cmangos classic (dump SQL) les données utiles à PoGrinder.

Usage : python -I cmangos_extract.py ClassicDB_xxx.sql(.gz) data/
Sorties :
  cmangos_npcs.tsv   npc, type, rank, minLevel, maxLevel, orMin, orMax, grisParKill (cuivre, prix marchand)
  cmangos_drops.tsv  npc, item, taux (objets d'artisanat, classe 7)
  cmangos_nodes.tsv  nomNœud, item, quantitéMoyenneParNœud
"""
import sys, gzip, re, os, collections
src, outdir = sys.argv[1], sys.argv[2]
op = gzip.open if src.endswith('.gz') else open
text = op(src, 'rt', encoding='utf8', errors='replace').read()

def columns(table):
    m = re.search(r'CREATE TABLE `%s` \((.*?)\n\) ENGINE' % table, text, re.S)
    return re.findall(r'^\s*`(\w+)`', m.group(1), re.M)

def rows(table):
    cols = columns(table)
    for m in re.finditer(r'^INSERT INTO `%s` VALUES (.*?);$' % table, text, re.M):
        s, i, n = m.group(1), 0, len(m.group(1))
        while i < n:
            if s[i] != '(':
                i += 1; continue
            i += 1; vals, cur, inq = [], [], False
            while True:
                c = s[i]
                if inq:
                    if c == '\\': cur.append(s[i + 1]); i += 2; continue
                    if c == "'": inq = False
                    else: cur.append(c)
                    i += 1; continue
                if c == "'": inq = True; i += 1; continue
                if c in ',)':
                    v = ''.join(cur); vals.append(v); cur = []
                    i += 1
                    if c == ')': break
                    continue
                cur.append(c); i += 1
            yield dict(zip(cols, vals))

num = lambda x: float(x) if x not in ('', 'NULL') else 0.0
items = {int(r['entry']): (int(r['class']), int(r['Quality']), int(r['SellPrice'])) for r in rows('item_template')}

def table_entries(table):
    t = collections.defaultdict(list)
    for r in rows(table):
        t[int(r['entry'])].append((int(r['item']), num(r['ChanceOrQuestChance']), int(r['groupid']),
                                   int(num(r['mincountOrRef'])), int(num(r['maxcount']))))
    return t
ref = table_entries('reference_loot_template')
creature = table_entries('creature_loot_template')
gobj = table_entries('gameobject_loot_template')

def expand(entries, mult=1.0, depth=0):
    """-> {item: nombre moyen par loot}. Groupes : les objets à chance 0 se partagent le reste."""
    out = collections.Counter()
    groups = collections.defaultdict(list)
    for e in entries: groups[e[2]].append(e)
    for g, es in groups.items():
        if g == 0:
            weighted = [(e, abs(e[1]) / 100.0) for e in es]
        else:
            explicit = sum(abs(e[1]) for e in es if e[1] != 0)
            zeros = [e for e in es if e[1] == 0]
            share = max(0.0, 100.0 - explicit) / len(zeros) if zeros else 0
            weighted = [(e, (abs(e[1]) if e[1] != 0 else share) / 100.0) for e in es]
        for (item, ch, _, mn, mx), p in weighted:
            if mn < 0:   # référence
                if depth < 4: out.update({k: v * p * mx for k, v in expand(ref.get(-mn, []), 1.0, depth + 1).items()})
            else:
                out[item] += p * (mn + max(mn, mx)) / 2.0
    return {k: v * mult for k, v in out.items()}

os.makedirs(outdir, exist_ok=True)
fn = open(os.path.join(outdir, 'cmangos_npcs.tsv'), 'w', encoding='utf8', newline='\n')
fd = open(os.path.join(outdir, 'cmangos_drops.tsv'), 'w', encoding='utf8', newline='\n')
nn = nd = 0
for r in rows('creature_template'):
    npc = int(r['Entry']); loot = int(num(r['LootId']))
    drops = expand(creature.get(loot, [])) if loot else {}
    gray = 0.0
    for it, q in drops.items():
        cls, qual, sell = items.get(it, (None, None, 0))
        if qual == 0: gray += q * sell
        if cls == 7 and q >= 0.001:
            fd.write('%d\t%d\t%.4f\n' % (npc, it, q)); nd += 1
    fn.write('%d\t%s\t%s\t%s\t%s\t%d\t%d\t%.1f\n' % (npc, r['CreatureType'], r['Rank'], r['MinLevel'], r['MaxLevel'],
                                               int(num(r['MinLootGold'])), int(num(r['MaxLootGold'])), gray)); nn += 1
fn.close(); fd.close()

fo = open(os.path.join(outdir, 'cmangos_nodes.tsv'), 'w', encoding='utf8', newline='\n')
no = 0
seen = set()
for r in rows('gameobject_template'):
    if r['type'] != '3': continue     # 3 = coffre / nœud récoltable
    name = r['name']; loot = int(num(r['data1']))
    if not loot or name in seen or loot not in gobj: continue
    seen.add(name)
    for it, q in expand(gobj[loot]).items():
        if items.get(it, (None,))[0] == 7 and q >= 0.01:
            fo.write('%s\t%d\t%.3f\n' % (name, it, q)); no += 1
fo.close()
print('npcs', nn, 'drops', nd, 'nodes', no)
