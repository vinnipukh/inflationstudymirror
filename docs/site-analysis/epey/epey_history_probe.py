"""epey_history_probe — how much price history an epey.com product has.

Browser-assisted (Cloudflare-cookie-protected): run inside a Camoufox session.
Steps: GET product page -> detect #fiyatgecmisi -> extract id&fiyat from inline
chart JS -> POST /kat/fg/ -> summarize ranges (6/12/36 mo windows, contiguous).

Interpretation:
  - no #fiyatgecmisi => not price-tracked (new listing w/o sellers,
    one-off classifieds like used cars, non-retail items).
  - range ids 36/12/6 = 3yr/1yr/6mo windows; together = full tracked history.
  - point density varies: sparse windows = niche/old products tracked lightly.
"""
"""
Verified 2026-09-05:
  iPhone SE 2 (2020)  -> 1075 days, deepest 36mo (2023-09-06 -> 2026-09-05)
  Samsung Galaxy J2   -> 455 days, deepest 36mo (sparse: 50 pts in 12mo window)
  Poco X8             -> no history (just listed)
  2014 Volvo XC60     -> no history (specs-only car page)
"""
import subprocess, json, time, datetime
from collections import Counter

def evaljs(js):
    return subprocess.run(['camoufox-cli','eval',js], capture_output=True, text=True, timeout=60).stdout

def _read_netlog(timeout=25):
    for _ in range(timeout):
        v = evaljs("() => document.getElementById('__netlog') ? document.getElementById('__netlog').value : 'NONE'").strip()
        if v and v != 'FETCH':
            return v
        time.sleep(1)
    return 'TIMEOUT'

def probe_epey_history(product_url):
    evaljs("() => { document.getElementById('__netlog')?.remove(); let n=document.createElement('textarea'); n.id='__netlog'; n.style.display='none'; document.body.appendChild(n); return 'ok'; }")
    js = """() => {
      document.getElementById('__netlog').value='FETCH';
      fetch('URL', {credentials:'include'}).then(r=>r.text()).then(t=>{
        const hasHist = t.includes('id="fiyatgecmisi"');
        const mfg = t.match(/id=(\d+)&fiyat=([\d.]+)/);
        document.getElementById('__netlog').value = JSON.stringify({hasHist, fgMatch: mfg ? [mfg[1], mfg[2]] : null});
      }).catch(e=>{ document.getElementById('__netlog').value='ERR:'+e; });
      return 'started';
    }""".replace('URL', product_url)
    evaljs(js)
    meta = json.loads(_read_netlog())
    if not meta.get('hasHist') or not meta.get('fgMatch'):
        return {'has_history': False}
    pid, fiyat = meta['fgMatch']
    js2 = f"""() => {{
      document.getElementById('__netlog').value='FETCH';
      fetch('/kat/fg/', {{method:'POST', credentials:'include', headers:{{'Content-Type':'application/x-www-form-urlencoded'}}, body:'id={pid}&fiyat={fiyat}'}})
        .then(r=>r.text()).then(t=>{{ document.getElementById('__netlog').value='LEN:'+t.length+'\n'+t; }})
        .catch(e=>{{ document.getElementById('__netlog').value='ERR:'+e; }});
      return 'started';
    }}"""
    evaljs(js2)
    raw = _read_netlog(timeout=25)
    if not raw.startswith('LEN:'):
        return {'has_history': True, 'pid': pid, 'error': raw[:150]}
    data = json.loads(raw.split('\n',1)[1])
    def parse(x): return datetime.datetime.strptime(x,'%d.%m.%Y').date()
    ranges = Counter(r for _,_,r in data)
    summary = {}
    for r in sorted(ranges):
        pts = [x for x in data if x[2]==r]
        summary[f'{r}mo'] = {'from': str(parse(pts[0][0])), 'to': str(parse(pts[-1][0])), 'points': len(pts)}
    days = len({parse(d) for d,_,_ in data})
    return {'has_history': True, 'pid': pid, 'unique_days': days,
            'deepest_range_months': max(ranges), 'ranges': summary}

if __name__ == '__main__':
    import sys
    for url in sys.argv[1:]:
        print(json.dumps(probe_epey_history(url), ensure_ascii=False))
