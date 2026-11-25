"""Génère FarmDB.lua pour PoGrinder (WoW Forever).

Sources, par ordre de priorité :
  1. Le journal de loot de PoGrinder (SavedVariables PoGrinderLog) : taux mesurés.
  2. GatherMate2 : nœuds perso (SavedVariables) et GatherMate2_Data, pour les points de récolte.
  3. QuestieDB Forever : spawns de mobs et d'objets, sources de drop, taux wowhead connus.
  4. Une table manuelle pour les tissus (a priori « humanoïdes de tel niveau »).

Usage : python -I gen.py "<WoW>/_forever_/Interface/AddOns" [sortie FarmDB.lua]
Si les tests échouent, l'ancien FarmDB.lua est conservé.
"""
import sys, os, re, glob, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from qdb import DB
from luatable import load_globals

ADDONS = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ADDONS, 'PoGrinder', 'FarmDB.lua')
WTF = os.environ.get('POGRIND_WTF') or os.path.normpath(os.path.join(ADDONS, '..', '..', 'WTF'))

K_PRIOR = 20          # poids de l'a priori (en kills) dans le lissage bayésien
MIN_KILLS = 20        # sans a priori, nombre de kills avant d'afficher un taux mesuré
MIN_OPENS = 5         # nœuds/sources mesurés avant d'ajouter une source inconnue de Questie

def log(*a): print('[gen]', *a)
def D(x):
    if isinstance(x, list): return {i + 1: v for i, v in enumerate(x)}
    return x if isinstance(x, dict) else {}
def s(x): return x.decode('utf8', 'replace') if isinstance(x, bytes) else (x or '')
def readtxt(p): return open(p, encoding='utf8', errors='replace').read()

# ---------- QuestieDB ----------
db = DB(os.path.join(ADDONS, 'QuestieDB', 'QuestieDB_Forever.toc'))
SUPPORT = os.path.join(ADDONS, 'QuestieDB', 'support', 'Forever')

rates = collections.defaultdict(dict)      # taux wowhead connus : [item][npc] = %
txt = readtxt(os.path.join(SUPPORT, 'DropTables', 'classicItemDrops.lua'))
txt = txt.split('wowheadData = [[', 1)[1].split(']]', 1)[0]
cur = None
for line in txt.splitlines():
    m = re.match(r'\s*\[(\d+)\] = \{', line)
    if m: cur = int(m.group(1)); continue
    m = re.match(r'\s*\[(\d+)\] = ([\d.]+)', line)
    if m and cur: rates[cur][int(m.group(1))] = float(m.group(2)) / 100.0

ui2area = {}
p = os.path.join(SUPPORT, 'Zones', 'uiMapIdToAreaId.lua')
if os.path.exists(p):
    for a, b in re.findall(r'\[(\d+)\]\s*=\s*(\d+)', readtxt(p)): ui2area[int(a)] = int(b)
log('uiMap->area :', len(ui2area))

# ---------- cmangos classic (a priori : PO, gris, taux de drop, rendement des nœuds) ----------
DATA = os.path.join(HERE, 'data')
cm_npc = {}       # npc -> (type, rank, orMoyen, grisParKill)
cm_drops = collections.defaultdict(dict)   # item -> {npc: taux}
cm_nodes = collections.defaultdict(dict)   # nomNœud(minuscule) -> {item: qté}
def tsv(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p): log('absent :', p); return []
    return [l.rstrip('\n').split('\t') for l in open(p, encoding='utf8')]
for r in tsv('cmangos_npcs.tsv'):
    cm_npc[int(r[0])] = (int(r[1]), int(r[2]), (int(r[5]) + int(r[6])) / 2.0, float(r[7]))
for r in tsv('cmangos_drops.tsv'):
    cm_drops[int(r[1])][int(r[0])] = float(r[2])
for r in tsv('cmangos_nodes.tsv'):
    cm_nodes[r[0].lower()][int(r[1])] = float(r[2])
for it, d in cm_drops.items():
    for n, q in d.items(): rates[it].setdefault(n, q)   # wowhead prioritaire, cmangos sinon
log('cmangos : %d mobs, %d objets avec taux, %d types de nœuds' % (len(cm_npc), len(cm_drops), len(cm_nodes)))

objcache, npccache = {}, {}
def obj(i):
    if i not in objcache:
        r = D(db.row('Object', i))
        objcache[i] = (s(r.get(1)), D(db.field('Object', i, 4)) if r else {})
    return objcache[i]
def npc(i):
    if i not in npccache:
        r = D(db.row('Npc', i))
        npccache[i] = (s(r.get(1)), r.get(4) or 0, r.get(5) or 0, r.get(6) or 0,
                       s(r.get(13)), D(db.field('Npc', i, 7)) if r else {})
    return npccache[i]

BAD_OBJ = re.compile(r'chest|crate|box|barrel|trunk|coffer|cache|sack|bag|footlocker|strongbox|cask|pile|stash|supplies|locker', re.I)
items = {}                                  # [itemID] = name, uniquement classe 7 (artisanat)
item_objs = collections.defaultdict(set)    # [itemID] = {objectID}
item_npcs = collections.defaultdict(set)    # [itemID] = {npcID}
obj_by_name = collections.defaultdict(set)  # nom d'objet -> {objectID}
for iid in db.ids('Item'):
    r = D(db.row('Item', iid))
    if r.get(12) != 7: continue
    items[iid] = s(r.get(1))
    for o in (db.field('Item', iid, 3) or []):
        name, _ = obj(o)
        if not BAD_OBJ.search(name):
            item_objs[iid].add(o); obj_by_name[name.lower()].add(o)
    for n in (db.field('Item', iid, 2) or []): item_npcs[iid].add(n)
log('objets d\'artisanat Questie :', len(items))
for it in items:
    item_npcs[it].update(cm_drops.get(it, {}).keys())

# ---------- Journal PoGrinder ----------
kills, loots, money = collections.Counter(), {}, {}
for f in glob.glob(os.path.join(WTF, 'Account', '*', 'SavedVariables', 'PoGrinder.lua')):
    try:
        g = load_globals(f).get('PoGrinderLog') or {}
        for k, v in D(g.get('kills')).items(): kills[int(k)] += v
        for k, e in D(g.get('loots')).items():
            cur = loots.setdefault(k, {'opens': 0, 'items': collections.Counter()})
            cur['opens'] += e.get('opens', 0)
            for it, q in D(e.get('items')).items(): cur['items'][int(it)] += q
        for k, e in D(g.get('money')).items():
            m = money.setdefault(int(k), [0, 0.0]); m[0] += e.get('corpses', 0); m[1] += e.get('copper', 0)
        log('journal lu :', f)
    except Exception as ex:
        log('journal illisible, ignoré :', f, ex)
log('kills mesurés :', sum(kills.values()), '| sources fouillées :', sum(e['opens'] for e in loots.values()))

# Sources découvertes par le journal mais absentes de Questie (ex. tissus)
for key, e in loots.items():
    kind, _, sid = key.partition(':'); sid = int(sid)
    for it, q in e['items'].items():
        if it not in items: continue
        if kind == 'n' and kills[sid] >= MIN_KILLS: item_npcs[it].add(sid)
        if kind == 'o' and e['opens'] >= MIN_OPENS: item_objs[it].add(sid)

# ---------- GatherMate2 ----------
gm_names = {}   # nodeID GatherMate -> nom anglais
p = os.path.join(ADDONS, 'GatherMate2', 'Constants.lua')
if os.path.exists(p):
    t = readtxt(p).split('GatherMate.nodeIDs', 1)[0]
    for name, nid in re.findall(r'\["([^"]+)"\]\s*=\s*(\d+)', t): gm_names.setdefault(int(nid), name)
    for name, nid in re.findall(r'\["([^"]+)"\]\s*=\s*\{\s*id\s*=\s*(\d+)', t): gm_names.setdefault(int(nid), name)
log('nœuds GatherMate connus :', len(gm_names))

def gm_tables(globs):
    for name, t in globs.items():
        if re.search(r'(Herb|Mine|Fish|Gas|Treasure)', name) and isinstance(t, dict):
            yield name, t
gm_count = collections.defaultdict(collections.Counter)   # [(area)][objectName] = nb nœuds
gm_kind = {}   # nom de nœud (minuscule) -> 'm' (minage) / 'h' (herboristerie)
def add_gm(globs, label):
    n = 0
    for tname, t in gm_tables(globs):
        for mapid, nodes in t.items():
            if not isinstance(nodes, dict): continue
            area = ui2area.get(mapid)
            if not area: continue
            per = collections.Counter(nodes.values())
            for nid, c in per.items():
                nm = gm_names.get(nid)
                if nm:
                    gm_count[area][nm.lower()] = max(gm_count[area][nm.lower()], c); n += c
                    if nid // 100 in (2, 4): gm_kind[nm.lower()] = 'm' if nid // 100 == 2 else 'h'
    log('GatherMate', label, ':', n, 'nœuds')
for f in glob.glob(os.path.join(ADDONS, 'GatherMate2_Data', 'Forever', '*Data.lua')):
    if os.path.basename(f) == 'GatherMateData.lua': continue
    try: add_gm(load_globals(f), os.path.basename(f))
    except Exception as ex: log('GatherMate2_Data illisible :', f, ex)
for f in glob.glob(os.path.join(WTF, 'Account', '*', 'SavedVariables', 'GatherMate2.lua')):
    try: add_gm(load_globals(f), 'perso')
    except Exception as ex: log('GatherMate2 perso illisible :', f, ex)

# ---------- Tissus : a priori manuel ----------
CLOTH = {2589: (5, 22), 2592: (15, 32), 4306: (24, 42), 4338: (33, 52), 14047: (46, 63)}
NOT_HUMANOID = re.compile(r'wolf|boar|spider|bear|raptor|crocolisk|cat|panther|tiger|lion|gorilla|kodo|strider|hyena|vulture|buzzard|bat\b|owl|crab|turtle|basilisk|scorpid|wasp|elemental|ooze|slime|ghost|skeleton|zombie|ghoul|wisp|treant|whelp|drake|dragon|serpent|snake|worg|stag|deer|rabbit|rat\b|hawk|condor|lurker|stalker|prowler|crawler|silithid|beetle|bug|moth|toad|frog|horse|ram\b|goat|yeti|wendigo|imp\b|infernal|felhound|golem|construct|shredder|harvester|tauren|elk|bird|raven|eagle|python|lizard|thunder|wind|fire|water|earth|air\b', re.I)
cloth_npcs = collections.defaultdict(set)
for nid in db.ids('Npc'):
    name, lo, hi, rank, friendly, sp = npc(nid)
    if friendly or rank not in (0, 1) or not sp: continue
    if nid in cm_npc:
        if cm_npc[nid][0] != 7: continue          # 7 = humanoïde
    elif NOT_HUMANOID.search(name): continue
    for it, (a, b) in CLOTH.items():
        if lo and hi and lo <= b and hi >= a: cloth_npcs[it].add(nid)
for it in CLOTH:
    items.setdefault(it, items.get(it) or {2589: 'Linen Cloth', 2592: 'Wool Cloth', 4306: 'Silk Cloth', 4338: 'Mageweave Cloth', 14047: 'Runecloth'}[it])

# ---------- Agrégation ----------
def mob_rate(it, nid):
    """Taux lissé ; None si inconnu."""
    prior = rates.get(it, {}).get(nid)
    k = kills[nid]
    obs = loots.get('n:%d' % nid, {}).get('items', {}).get(it, 0)
    if prior is not None: return (obs + prior * K_PRIOR) / (k + K_PRIOR), k > 0
    if k >= MIN_KILLS: return obs / k, True
    return None, False

res = {}
for it, name in items.items():
    zones = collections.defaultdict(lambda: {'n': 0, 'gm': 0, 'm': 0.0, 'lo': 999, 'hi': 0, 'u': 0, 'meas': 0})
    for o in item_objs[it]:
        oname, sp = obj(o)
        for z, pts in sp.items():
            if isinstance(z, int) and z > 0: zones[z]['n'] += len(pts)
        for z, cnt in gm_count.items():
            if oname.lower() in cnt: zones[z]['gm'] = max(zones[z]['gm'], cnt[oname.lower()])
        if loots.get('o:%d' % o, {}).get('opens', 0) >= MIN_OPENS:
            for z in sp:
                if z in zones: zones[z]['meas'] = 1
    srcs = [(n, False) for n in item_npcs[it]] + [(n, True) for n in cloth_npcs.get(it, ()) if n not in item_npcs[it]]
    for nid, guess in srcs:
        _, lo, hi, _, _, sp = npc(nid)
        rate, measured = mob_rate(it, nid)
        for z, pts in sp.items():
            if not (isinstance(z, int) and z > 0): continue
            zz = zones[z]
            if rate is None: zz['u'] += len(pts)
            else: zz['m'] += len(pts) * rate
            if measured: zz['meas'] = 1
            if lo: zz['lo'] = min(zz['lo'], lo); zz['hi'] = max(zz['hi'], hi or lo)
    out = []
    for z, v in zones.items():
        nodes = v['gm'] if v['gm'] else v['n']   # GatherMate prioritaire
        if nodes or v['m'] or v['u']:
            out.append((z, nodes, v['m'], 0 if v['lo'] == 999 else v['lo'], v['hi'], v['u'], v['meas']))
    if out:
        out.sort(key=lambda t: t[1] + t[2] + t[5] * 0.002, reverse=True)
        res[it] = (name, out[:6])


# ---------- Base par zone (étape 3) ----------
K_MONEY = 10   # poids de l'a priori cmangos (en corps) pour les PO
def kind_of(name):
    n = name.lower()
    if n in gm_kind: return gm_kind[n]
    return 'm' if re.search(r'vein|deposit|filon|gisement', n) else 'h'

# nœuds : nom -> {item: qté par nœud}
node_items = collections.defaultdict(dict)
for it in items:
    for o in item_objs[it]:
        nm = obj(o)[0].lower()
        if nm: node_items[nm].setdefault(it, None)
for nm in list(node_items):
    cm = cm_nodes.get(nm, {})
    for it in node_items[nm]:
        node_items[nm][it] = cm.get(it) or (1.0 if it == max(node_items[nm], key=lambda x: cm.get(x, 0)) else 0.05)
zone_nodes = collections.defaultdict(dict)   # area -> {nom: nb}
for nm in node_items:
    objs = set()
    for it in node_items[nm]: objs |= {o for o in item_objs[it] if obj(o)[0].lower() == nm}
    q = collections.Counter()
    for o in objs:
        for z, pts in obj(o)[1].items():
            if isinstance(z, int) and z > 0: q[z] += len(pts)
    for z, c in q.items(): zone_nodes[z][nm] = c
    for z, cnt in gm_count.items():
        if nm in cnt: zone_nodes[z][nm] = cnt[nm]          # GatherMate prioritaire

def money_per_kill(nid):
    prior = cm_npc.get(nid, (0, 0, None, 0))[2]
    corpses, copper = money.get(nid, (0, 0.0))
    if prior is None: return copper / corpses if corpses >= 10 else None
    return (copper + prior * K_MONEY) / (corpses + K_MONEY)

# mobs : area -> tranche de niveau (5 niv.) -> agrégats
bands = collections.defaultdict(lambda: collections.defaultdict(lambda: {'s': 0, 'lo': 999, 'hi': 0, 'or': 0.0, 'orS': 0, 'gris': 0.0, 'grisS': 0, 'drops': collections.Counter()}))
mob_items = collections.defaultdict(dict)   # npc -> {item: taux}
for it in items:
    for n in item_npcs[it] | cloth_npcs.get(it, set()):
        r, _ = mob_rate(it, n)
        if r: mob_items[n][it] = r
for nid in db.ids('Npc'):
    name, lo, hi, rank, friendly, sp = npc(nid)
    if friendly or not sp or not lo or rank not in (0,): continue
    if cm_npc.get(nid, (0,))[0] == 8: continue          # bestioles
    mk, gr = money_per_kill(nid), cm_npc.get(nid, (0, 0, 0, None))[3]
    for z, pts in sp.items():
        if not (isinstance(z, int) and z > 0): continue
        b = bands[z][(lo + hi) // 2 // 5]
        c = len(pts); b['s'] += c
        b['lo'] = min(b['lo'], lo); b['hi'] = max(b['hi'], hi or lo)
        if mk is not None: b['or'] += mk * c; b['orS'] += c
        if gr is not None: b['gris'] += gr * c; b['grisS'] += c
        for it, r in mob_items.get(nid, {}).items(): b['drops'][it] += r * c

zones_out = {}
for z in set(zone_nodes) | set(bands):
    nodes = [(nm, c, node_items[nm]) for nm, c in zone_nodes.get(z, {}).items() if c >= 3]
    mobs = []
    for key, b in bands.get(z, {}).items():
        if b['s'] < 10: continue
        drops = sorted(((it, v / b['s']) for it, v in b['drops'].items() if v / b['s'] >= 0.002), key=lambda t: -t[1])[:8]
        mobs.append((b['lo'], b['hi'], b['s'], b['or'] / b['orS'] if b['orS'] else -1, b['gris'] / b['grisS'] if b['grisS'] else -1, drops))
    if nodes or mobs: zones_out[z] = (nodes, sorted(mobs))
log('zones :', len(zones_out))

# ---------- Tests de cohérence ----------
def check():
    errs = []
    if len(res) < 200: errs.append('seulement %d objets' % len(res))
    for it, nm in ((2770, 'Copper Ore'), (2771, 'Tin Ore'), (2772, 'Iron Ore'), (2447, 'Peacebloom'), (765, 'Silverleaf')):
        if it not in res: errs.append('%s (%d) absent' % (nm, it)); continue
        if res[it][1][0][1] < 20: errs.append('%s : moins de 20 points de récolte dans la meilleure zone' % nm)
    if 2770 in res and not any(z[0] in (1, 12, 14, 40, 85, 215, 141) for z in res[2770][1]):
        errs.append('Copper Ore : aucune zone de départ dans le top 6')
    if len(zones_out) < 40: errs.append('seulement %d zones' % len(zones_out))
    dz = zones_out.get(14) or zones_out.get(12)
    if not dz or not dz[1]: errs.append('Durotar/Elwynn : pas de mobs')
    elif not any(m[3] > 0 for m in dz[1]): errs.append('Durotar/Elwynn : pas de PO par kill')
    return errs

errs = check()
if errs:
    log('ÉCHEC des tests, FarmDB.lua conservé :'); [log('  -', e) for e in errs]; sys.exit(1)

def luastr(x): return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'
tmp = OUT + '.tmp'
with open(tmp, 'w', encoding='utf8', newline='\n') as f:
    f.write('-- GÉNÉRÉ par tools/gen.py (QuestieDB + GatherMate2 + journal PoGrinder). Ne pas éditer.\n')
    f.write('-- [itemID] = { {areaID, pointsRécolte, dropsMobsAttendus, lvlMin, lvlMax, spawnsTauxInconnu, mesuré}, ... }\n')
    f.write('local _, ns = ...\nns.FarmDB = {\n')
    for it in sorted(res):
        f.write('  [%d]={%s},\n' % (it, ','.join('{%d,%d,%.2f,%d,%d,%d,%d}' % z for z in res[it][1])))
    f.write('}\nns.FarmNames = {\n')
    for it in sorted(res):
        f.write('  [%d]=%s,\n' % (it, luastr(res[it][0])))
    f.write('}\n')
os.replace(tmp, OUT)

ZOUT = os.path.join(os.path.dirname(OUT), 'ZoneDB.lua')
with open(ZOUT + '.tmp', 'w', encoding='utf8', newline='\n') as f:
    f.write('-- GÉNÉRÉ par tools/gen.py. Ne pas éditer.\n')
    f.write('-- [areaID] = { n = { {type m/h, nbNœuds, {item, qté, ...}}, ... },\n')
    f.write('--   m = { {lvlMin, lvlMax, nbSpawns, POparKill (-1 inconnu), grisParKill (-1 inconnu), {item, tauxParKill, ...}}, ... } }\n')
    f.write('local _, ns = ...\nns.ZoneDB = {\n')
    for z in sorted(zones_out):
        nodes, mobs = zones_out[z]
        ns_ = ','.join('{"%s",%d,{%s}}' % (kind_of(nm), c, ','.join('%d,%.3f' % (it, q) for it, q in its.items())) for nm, c, its in nodes)
        ms_ = ','.join('{%d,%d,%d,%.1f,%.1f,{%s}}' % (lo, hi, sp_, mo, gr, ','.join('%d,%.4f' % d for d in dr)) for lo, hi, sp_, mo, gr, dr in mobs)
        f.write('  [%d]={n={%s},m={%s}},\n' % (z, ns_, ms_))
    f.write('}\nns.UiToArea = {%s}\n' % ','.join('[%d]=%d' % kv for kv in sorted(ui2area.items())))
os.replace(ZOUT + '.tmp', ZOUT)
log('OK :', len(zones_out), 'zones ->', ZOUT)
log('OK :', len(res), 'objets ->', OUT)
