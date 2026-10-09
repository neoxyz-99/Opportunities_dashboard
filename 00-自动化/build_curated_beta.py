#!/usr/bin/env python3
"""Build the existing static Pages dashboard from a small approved public projection."""
import argparse, hashlib, html, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'id','name','organization','type','geography','status','deadline','funding','eligibility','detail_url','application_url','verification','last_checked','reviewed_at'}
NOTICE='Actively curated Beta with incomplete coverage. Opportunity information can change. Confirm final application details on the linked official source.'

def validate(data):
    if set(data)!={'version','notice','opportunities'} or data['version']!=1 or data['notice']!=NOTICE: raise ValueError('Unexpected public projection')
    rows=data['opportunities']
    if len(rows)<5 or len({r['id'] for r in rows})!=len(rows): raise ValueError('At least five distinct approved opportunities required')
    for row in rows:
        if set(row)!=FIELDS or any(not isinstance(v,str) for v in row.values()): raise ValueError('Public field allowlist mismatch')
        if row['status'] not in ('Open','Rolling','Upcoming') or row['verification']!='Verified official source; current application evidence reviewed': raise ValueError('Unapproved lifecycle or provenance')
        if not row['name'] or not row['organization'] or not row['detail_url'].startswith('https://'): raise ValueError('Missing public identity')
        if row['application_url'] and not row['application_url'].startswith('https://'): raise ValueError('Invalid application URL')
    return rows

def render(data):
    rows=validate(data);esc=lambda v:html.escape(v,quote=True)
    cards=[]
    for row in rows:
        fields=''.join('<div class="field"><b>'+esc(label)+'</b><span>'+esc(row[key])+'</span></div>' for label,key in [('Organization','organization'),('Geography','geography'),('Funding · source statement','funding'),('Eligibility','eligibility')])
        apply='<a href="'+esc(row['application_url'])+'" target="_blank" rel="noopener noreferrer">Application page ↗</a>' if row['application_url'] else ''
        cards.append('<article class="card" data-search="'+esc(' '.join(row.values()).lower())+'" data-type="'+esc(row['type'])+'"><header class="card-heading"><div><h2 class="title">'+esc(row['name'])+'</h2><div class="chips"><span class="chip">'+esc(row['type'])+'</span><span class="chip">'+esc(row['status'])+' · as reviewed</span></div></div><div class="deadline"><span>Verified deadline</span><strong>'+esc(row['deadline'])+'</strong></div></header><div class="details"><div class="detail-grid">'+fields+'</div><p class="verification">✓ '+esc(row['verification'])+'</p><p class="meta-check">Source last checked: '+esc(row['last_checked'])+' · Reviewed: '+esc(row['reviewed_at'])+'</p><div class="links"><a href="'+esc(row['detail_url'])+'" target="_blank" rel="noopener noreferrer">Official details ↗</a>'+apply+'</div></div></article>')
    options=''.join('<option>'+esc(t)+'</option>' for t in sorted({r['type'] for r in rows}))
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>International Opportunity — Beta</title><link rel="stylesheet" href="beta.css"></head><body><div class="shell"><header class="hero"><div><p class="eyebrow">CURATED INTERNATIONAL OPPORTUNITIES</p><h1>International Opportunity <span class="beta-label">Beta</span></h1><p>Fellowships, research funding and policy opportunities.</p></div></header><p class="beta-notice">'''+esc(NOTICE)+'''</p><section class="stats"><div class="stat"><strong>'''+str(len(rows))+'''</strong><span>Verified opportunities</span></div><div class="stat"><strong>Curated</strong><span>Current application evidence</span></div></section><section class="toolbar"><div class="search-row"><label class="search-label" for="search">Search opportunities<input id="search" type="search" placeholder="Search name, organization or eligibility"></label><label for="type">Opportunity type<select id="type"><option value="">All types</option>'''+options+'''</select></label></div></section><p id="count" aria-live="polite">'''+str(len(rows))+''' opportunities</p><main class="list" id="list">'''+''.join(cards)+'''</main><p id="empty" hidden>No matching opportunities. Try another search.</p><footer class="site-footer">International Opportunity — Beta · Source statements are shown only where supported. Eligibility may be restricted; check the official call for complete conditions.</footer></div><script>
const search=document.getElementById('search'), type=document.getElementById('type');
function filter(){let count=0; document.querySelectorAll('article.card').forEach(card=>{card.hidden=!(card.dataset.search.includes(search.value.trim().toLowerCase())&&(!type.value||card.dataset.type===type.value));if(!card.hidden)count++;});document.getElementById('count').textContent=count+' opportunities';document.getElementById('empty').hidden=count!==0;}
search.addEventListener('input',filter);type.addEventListener('change',filter);
</script></body></html>'''

def build(data,destination):
    output=Path(destination);output.mkdir(parents=True,exist_ok=True)
    (output/'index.html').write_text(render(data),encoding='utf-8')
    (output/'opportunities.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'beta.css').write_bytes((ROOT/'docs/beta.css').read_bytes())
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();print(json.dumps(build(json.loads(args.data.read_text()),args.output)))
if __name__=='__main__':main()
