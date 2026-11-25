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
WTF = os.path.normpath(os.path.join(ADDONS, '..', '..', 'WTF'))

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

# ---------- Journal PoGrinder ----------
kills, loots = collections.Counter(), {}
for f in glob.glob(os.path.join(WTF, 'Account', '*', 'SavedVariables', 'PoGrinder.lua')):
    try:
        g = load_globals(f).get('PoGrinderLog') or {}
        for k, v in D(g.get('kills')).items(): kills[int(k)] += v
        for k, e in D(g.get('loots')).items():
            cur = loots.setdefault(k, {'opens': 0, 'items': collections.Counter()})
            cur['opens'] += e.get('opens', 0)
            for it, q in D(e.get('items')).items(): cur['items'][int(it)] += q
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
    for name, nid in re.findall(r'\[NL\["([^"]+)"\]\]\s*=\s*(\d+)', readtxt(p)): gm_names[int(nid)] = name
log('nœuds GatherMate connus :', len(gm_names))

def gm_tables(globs):
    for name, t in globs.items():
        if re.search(r'(Herb|Mine|Fish|Gas|Treasure)', name) and isinstance(t, dict):
            yield name, t
gm_count = collections.defaultdict(collections.Counter)   # [(area)][objectName] = nb nœuds
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
                if nm: gm_count[area][nm.lower()] = max(gm_count[area][nm.lower()], c); n += c
    log('GatherMate', label, ':', n, 'nœuds')
for f in glob.glob(os.path.join(ADDONS, 'GatherMate2_Data', '*.lua')):
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
    if friendly or rank not in (0, 1) or not sp or NOT_HUMANOID.search(name): continue
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

# ---------- Tests de cohérence ----------
def check():
    errs = []
    if len(res) < 200: errs.append('seulement %d objets' % len(res))
    for it, nm in ((2770, 'Copper Ore'), (2771, 'Tin Ore'), (2772, 'Iron Ore'), (2447, 'Peacebloom'), (765, 'Silverleaf')):
        if it not in res: errs.append('%s (%d) absent' % (nm, it)); continue
        if res[it][1][0][1] < 20: errs.append('%s : moins de 20 points de récolte dans la meilleure zone' % nm)
    if 2770 in res and not any(z[0] in (1, 12, 14, 40, 85, 215, 141) for z in res[2770][1]):
        errs.append('Copper Ore : aucune zone de départ dans le top 6')
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
log('OK :', len(res), 'objets ->', OUT)
