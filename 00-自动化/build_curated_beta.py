#!/usr/bin/env python3
"""Build the existing static Pages dashboard from a small approved public projection."""
import argparse, hashlib, html, json, re
import copy
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from string import Template
# Standalone public date parser: identical conservative rules to the validated runtime.
MONTHS = {name: i for i, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}

DATE = re.compile(r"(?<!\d)(?:20\d\d-\d{1,2}-\d{1,2}|\d{1,2}[/.]\d{1,2}[/.]20\d\d|"
                  r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+20\d\d|"
                  r"\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?[,]?\s+20\d\d)(?!\d)", re.I)

def parse_date(value):
    # Numeric dot dates use the same ambiguity guard as slash dates. Never
    # infer a locale when both components could be the month.
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.20\d\d", value):
        return parse_date(value.replace('.', '/'))
    value = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value, flags=re.I).replace(",", "").replace(".", "")
    try:
        if re.fullmatch(r"20\d\d-\d{1,2}-\d{1,2}", value): return date.fromisoformat(value)
        if "/" in value:
            month, day, year = map(int, value.split("/"))
            if month <= 12 and day <= 12 and month != day: return None  # ambiguous locale
            return date(year, month, day) if month <= 12 else date(year, day, month)
        parts = value.split()
        if parts[0].isdigit(): day, name, year = parts
        else: name, day, year = parts
        month = next(v for k, v in MONTHS.items() if k.lower().startswith(name.lower()[:3]))
        return date(int(year), month, int(day))
    except (ValueError, StopIteration): return None

ROOT=Path(__file__).resolve().parents[1]
TEMPLATES=ROOT/'04-模板'
FIELDS={'id','name','organization','type','geography','status','deadline','funding','eligibility','detail_url','application_url','verification','last_checked','reviewed_at'}
NOTICE='Actively curated Beta with incomplete coverage. Opportunity information can change. Confirm final application details on the linked official source.'

def validate(data):
    if set(data)!={'version','notice','opportunities'} or data['version']!=1 or data['notice']!=NOTICE: raise ValueError('Unexpected public projection')
    rows=data['opportunities']
    if not isinstance(rows,list): raise ValueError('Opportunities must be a list')
    for row in rows:
        if set(row)!=FIELDS or any(not isinstance(v,str) for v in row.values()): raise ValueError('Public field allowlist mismatch')
        if row['status'] not in ('Open','Rolling','Upcoming') or row['verification']!='Verified official source; current application evidence reviewed': raise ValueError('Unapproved lifecycle or provenance')
        if not row['name'] or not row['organization'] or not row['detail_url'].startswith('https://'): raise ValueError('Missing public identity')
        if row['application_url'] and not row['application_url'].startswith('https://'): raise ValueError('Invalid application URL')
    if len({r['id'] for r in rows})!=len(rows): raise ValueError('Duplicate approved opportunity IDs')
    return rows

def deadline_day(row):
    literal=re.sub(r'(?<=\d),\s*(?=[A-Za-z])',' ',row['deadline'])
    cutoffs={d for m in DATE.finditer(literal) if (d:=parse_date(m.group())) is not None}
    return next(iter(cutoffs)) if len(cutoffs)==1 else None

def expiry_utc(row):
    """Operational expiry, not a guessed source time zone.

    A date-only deadline has certainly ended by noon UTC the next day, even
    in UTC-12. Never close it early by assuming midnight in the viewer's zone.
    """
    cutoff=deadline_day(row)
    if cutoff is None: return ''
    # Honor explicit source clock/zone pairs; never infer a zone from geography.
    literal=row['deadline']
    times=list(re.finditer(r'(?<!\d)(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)?',literal,re.I))
    zones=[]
    for pattern,zone in [(r'\bCET\b',timezone(timedelta(hours=1))),
                         (r'\bCEST\b',timezone(timedelta(hours=2))),
                         (r'\bEDT\b',timezone(timedelta(hours=-4))),
                         (r'\bEST\b',timezone(timedelta(hours=-5))),
                         (r'\bUTC\b|Coordinated Universal Time',timezone.utc),
                         (r'Pacific time',ZoneInfo('America/Los_Angeles')),
                         (r'Stockholm time',ZoneInfo('Europe/Stockholm'))]:
        if re.search(pattern,literal,re.I): zones.append(zone)
    if len(times)==1 and len(zones)==1:
        found=times[0];hour,minute=int(found[1]),int(found[2]);meridiem=(found[3] or '').lower().replace('.','')
        if minute<60 and ((meridiem and 1<=hour<=12) or (not meridiem and 0<=hour<24)):
            if meridiem: hour=hour%12+(12 if meridiem=='pm' else 0)
            return datetime(cutoff.year,cutoff.month,cutoff.day,hour,minute,tzinfo=zones[0]).astimezone(timezone.utc).isoformat()
    return datetime.combine(cutoff+timedelta(days=1),datetime.min.time(),timezone.utc).replace(hour=12).isoformat()

def current_projection(data, *, as_of=None):
    """Omit expired approved rows without changing their historical records.

    Calendar passage may remove currentness; it never grants verification or
    promotes an Upcoming record to Open. Unknown or multiple cutoff dates are
    left for review, not guessed. Same-day cutoffs require source time zones.
    """
    now=datetime.now(timezone.utc)
    today=date.fromisoformat(as_of) if isinstance(as_of,str) else as_of or now.date()
    rows=validate(data); result=copy.deepcopy(data); keep=[]
    for row in rows:
        cutoff=deadline_day(row)
        expired = bool(cutoff and cutoff < today) if as_of is not None else bool(expiry_utc(row) and datetime.fromisoformat(expiry_utc(row)) <= now)
        if expired: continue
        keep.append(copy.deepcopy(row))
    result['opportunities']=keep
    return result

def render(data, *, as_of=None):
    rows=validate(current_projection(data,as_of=as_of));esc=lambda v:html.escape(v,quote=True)
    def icon(name, extra=''):
        return '<svg class="icon'+(' '+extra if extra else '')+'" aria-hidden="true"><use href="#i-'+name+'"/></svg>'
    def type_icon(kind):
        return {'Research Grant':'grant','Research funding':'grant','Visiting Research':'book',
                'Visiting fellowship':'book','Fellowship':'briefcase','Traineeship':'briefcase',
                'Internship':'briefcase','Early-career research role':'briefcase',
                'Call for papers':'book'}.get(kind,'layers')
    cards=[]
    for row in rows:
        fields=''.join('<div class="field'+(' unresolved' if row[key] in ('Needs verification','Not stated') else '')+'"><b>'+esc(label)+'</b><span>'+esc(row[key])+'</span></div>' for label,key in [('Organization','organization'),('Geography','geography'),('Funding — source statement','funding'),('Eligibility','eligibility')])
        def source_link(url, label, secondary=False):
            return '<a'+(' class="secondary"' if secondary else '')+' href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+label+icon('external')+'<span class="sr-only"> (opens in a new tab)</span></a>'
        links=source_link(row['detail_url'],'Official details')
        if row['application_url']:
            links+=source_link(row['application_url'],'Application page',secondary=True)
        cards.append(
            '<article class="card" data-expires="'+esc(expiry_utc(row))+'" data-search="'+esc(' '.join(row.values()).lower())+'" data-type="'+esc(row['type'])+'" data-organization="'+esc(row['organization'])+'">'
            '<details class="record"><summary class="record-summary"><span class="record-icon">'+icon(type_icon(row['type']))+'</span><div class="record-heading">'
            '<h3 class="title">'+esc(row['name'])+'</h3><p class="organization">'+esc(row['organization'])+'</p><div class="chips"><span class="chip">'+esc(row['type'])+'</span><span class="chip status">'+esc(row['status'])+' — as reviewed</span></div></div>'
            '<div class="deadline"><span>Deadline — source statement</span><strong>'+esc(row['deadline'])+'</strong></div>'+icon('chevron','chevron')+'</summary>'
            '<div class="details"><div class="detail-grid">'+fields+'</div><div class="card-footer"><div><p class="verification">'+icon('shield')+esc(row['verification'])+'</p>'
            '<p class="meta-check"><span>Source last checked: '+esc(row['last_checked'])+'</span><span>Reviewed: '+esc(row['reviewed_at'])+'</span></p></div><div class="links">'+links+'</div></div></div></details></article>')
    types=sorted({r['type'] for r in rows})
    options=''.join('<option>'+esc(t)+'</option>' for t in types)
    navigation=''.join(
        '<button class="nav-type" type="button" data-type="'+esc(t)+'" aria-pressed="false" aria-label="'+esc(t)+'">'
        +icon(type_icon(t))+'<span class="nav-label">'+esc(t)+'</span><span class="nav-count">'+str(sum(r['type']==t for r in rows))+'</span></button>'
        for t in types)
    return Template((TEMPLATES/'curated-beta.html').read_text(encoding='utf-8')).substitute(
        count=len(rows), count_label=str(len(rows))+(' opportunity' if len(rows)==1 else ' opportunities'),
        organization_count=len({r['organization'] for r in rows}), type_count=len(types), navigation=navigation,
        empty_hidden='hidden' if rows else '', notice=esc(NOTICE), options=options, cards='\n'.join(cards))

def build(data,destination, *, as_of=None):
    data=current_projection(data,as_of=as_of)
    output=Path(destination);output.mkdir(parents=True,exist_ok=True)
    (output/'index.html').write_text(render(data,as_of=as_of),encoding='utf-8')
    (output/'opportunities.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'beta.css').write_bytes((ROOT/'docs/beta.css').read_bytes())
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--as-of',help='ISO calendar date for reproducible review');args=parser.parse_args();print(json.dumps(build(json.loads(args.data.read_text()),args.output,as_of=args.as_of)))
if __name__=='__main__':main()
