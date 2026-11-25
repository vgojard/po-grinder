# Lecteur minimal de la base QuestieDB "baked" (métadonnées TOC base64 + CBOR).
import base64, zlib, struct, sys
def cbor(b, i=0):
    ib=b[i]; mt=ib>>5; ai=ib&31; i+=1
    if ai<24: v=ai
    elif ai==24: v=b[i]; i+=1
    elif ai==25:
        if mt==7: return struct.unpack('>e',b[i:i+2])[0], i+2
        v=struct.unpack('>H',b[i:i+2])[0]; i+=2
    elif ai==26:
        if mt==7: return struct.unpack('>f',b[i:i+4])[0], i+4
        v=struct.unpack('>I',b[i:i+4])[0]; i+=4
    elif ai==27:
        if mt==7: return struct.unpack('>d',b[i:i+8])[0], i+8
        v=struct.unpack('>Q',b[i:i+8])[0]; i+=8
    else: raise ValueError('indef %d'%ib)
    if mt==0: return v,i
    if mt==1: return -1-v,i
    if mt==2: return b[i:i+v], i+v
    if mt==3: return b[i:i+v].decode('utf8','replace'), i+v
    if mt==4:
        out=[]
        for _ in range(v): x,i=cbor(b,i); out.append(x)
        return out,i
    if mt==5:
        out={}
        for _ in range(v):
            k,i=cbor(b,i); x,i=cbor(b,i); out[k]=x
        return out,i
    if mt==6: return cbor(b,i)
    if mt==7:
        return {20:False,21:True,22:None}.get(v,v),i
def load(path):
    d={}
    with open(path,encoding='utf8',errors='replace') as f:
        for line in f:
            if line.startswith('## X-'):
                k,_,v=line[3:].rstrip('\r\n').partition(': ')
                d[k]=v
    return d
class DB:
    def __init__(s,path): s.d=load(path)
    def stored(s,k):
        v=s.d.get(k)
        if v and v.startswith('~') and v.endswith('~'):
            n=int(v[1:-1]); v=''.join(s.d[k+'-%d'%j] for j in range(1,n+1))
        return v
    def dec(s,k,compressed=False):
        v=s.stored(k)
        if v is None: return None
        b=base64.b64decode(v)
        if compressed:
            for w in (15,-15,31):
                try: b=zlib.decompress(b,w); break
                except Exception: pass
        return cbor(b)[0]
    def ids(s,ent): return s.dec('X-%s-IDS'%ent,True)
    def row(s,ent,i): return s.dec('X-%s-%d-S'%(ent,i))
    def field(s,ent,i,f): return s.dec('X-%s-%d-%d'%(ent,i,f))
