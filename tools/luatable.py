# Parseur minimal de fichiers SavedVariables WoW (littéraux Lua : tables, chaînes, nombres, booléens).
import re
_tok = re.compile(r'''\s*(?:--\[\[.*?\]\]|--[^\n]*|(?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(?P<num>-?(?:0x[0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+))|(?P<name>[A-Za-z_]\w*)|(?P<sym>[{}\[\]=,;]))''', re.S)
def tokens(s):
    pos = 0
    while pos < len(s):
        m = _tok.match(s, pos)
        if not m:
            if s[pos:].strip() == '': return
            raise ValueError('lexer @%d: %r' % (pos, s[pos:pos+30]))
        pos = m.end()
        for k in ('str', 'num', 'name', 'sym'):
            v = m.group(k)
            if v is not None:
                yield k, v; break
def _unq(s):
    body = s[1:-1]
    return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t'}.get(m.group(1), m.group(1)), body)
class P:
    def __init__(s, txt): s.t = list(tokens(txt)); s.i = 0
    def peek(s): return s.t[s.i] if s.i < len(s.t) else (None, None)
    def next(s): v = s.t[s.i]; s.i += 1; return v
    def value(s):
        k, v = s.next()
        if k == 'str': return _unq(v)
        if k == 'num': return int(v, 16) if v.lower().startswith(('0x', '-0x')) else (float(v) if any(c in v for c in '.eE') else int(v))
        if k == 'name': return {'true': True, 'false': False, 'nil': None}.get(v, v)
        if v == '{': return s.table()
        raise ValueError('valeur inattendue %r' % v)
    def table(s):
        out, n = {}, 1
        while True:
            k, v = s.peek()
            if v == '}': s.next(); return out
            if v == '[':
                s.next(); key = s.value(); s.next(); s.next()  # ] =
                out[key] = s.value()
            elif k == 'name' and s.t[s.i + 1][1] == '=':
                s.next(); s.next(); out[v] = s.value()
            else:
                out[n] = s.value(); n += 1
            if s.peek()[1] in (',', ';'): s.next()
def load_globals(path):
    """Renvoie {nomGlobal: valeur} pour un fichier SavedVariables."""
    txt = open(path, encoding='utf8', errors='replace').read()
    p = P(txt); out = {}
    while p.i < len(p.t):
        k, name = p.next()
        if p.peek()[1] != '=': continue
        p.next(); out[name] = p.value()
    return out
