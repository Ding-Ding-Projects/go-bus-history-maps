#!/usr/bin/env python3
"""Build readable route-history PDF volumes from the checked archive data.

No network access or research is performed. Every source pattern and ordered
stop is included. Vector basemap forms are shared within each PDF. Run a
subset for review with --routes 52 31 69 --legacy yonge-c; omit filters for all.
"""
from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from datetime import date, datetime
import html
import io
import json
import math
from pathlib import Path
import re
import time

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
W, H = letter
M = 42
CW = W - 2 * M
GREEN = colors.HexColor('#20664f')
INK = colors.HexColor('#16392e')
MUTED = colors.HexColor('#56665f')
PALE = colors.HexColor('#e8f1eb')
PAPER = colors.HexColor('#fffefa')
LAND = colors.HexColor('#f5f2e9')
WATER = colors.HexColor('#e6f1f4')
BORDER = colors.HexColor('#d4ded6')
AMBER = colors.HexColor('#91662f')
AMBER_PALE = colors.HexColor('#f5eddf')
FONT_ROOT = Path('/usr/share/fonts/truetype/dejavu')
MONTHS = {name.lower(): i for i in range(1, 13) for name in (calendar.month_name[i], calendar.month_abbr[i])}


def clean(text):
    text = str(text or '')
    return text.translate(str.maketrans({'\u2010':'-', '\u2011':'-', '\u2012':'-', '\u2013':'-', '\u2014':' - ', '\u2212':'-', '\u2018':"'", '\u2019':"'", '\u201c':'"', '\u201d':'"', '\u2026':'...'}))


def esc(text):
    return html.escape(clean(text), quote=True)


def date_key(value):
    s = clean(value)
    iso = re.search(r'\b((?:19|20)\d{2})-(\d\d)(?:-(\d\d))?', s)
    if iso:
        return (int(iso[1]), int(iso[2]), int(iso[3] or 1))
    year = re.search(r'\b((?:19|20)\d{2})\b', s)
    if not year:
        return (9999, 1, 1)
    month = next((n for name, n in MONTHS.items() if re.search(r'\b'+re.escape(name)+r'\b', s.lower())), 1)
    day = re.search(r'\b([0-3]?\d)\s+(?:'+'|'.join(MONTHS)+r')\b', s.lower())
    return (int(year[1]), month, int(day[1]) if day else 1)


def pretty_date(s):
    try:
        d = date.fromisoformat(s)
        return f'{d.day} {d.strftime("%b %Y")}'
    except (ValueError, TypeError):
        return clean(s)


def date_range(first, last):
    return pretty_date(first) if first == last else f'{pretty_date(first)} - {pretty_date(last)}'


def exact_dates(values):
    """Exact compact calendar, preserving gaps rather than implying daily service."""
    months = defaultdict(list)
    for value in sorted(set(values)):
        d = date.fromisoformat(value)
        months[(d.year, d.month)].append(d.day)
    result = []
    for (year, month), days in months.items():
        runs = []
        start = end = days[0]
        for day in days[1:]:
            if day == end + 1:
                end = day
            else:
                runs.append(str(start) if start == end else f'{start}-{end}')
                start = end = day
        runs.append(str(start) if start == end else f'{start}-{end}')
        result.append(f'{calendar.month_abbr[month]} {year}: '+', '.join(runs))
    return '; '.join(result)


def projected(point):
    lon, lat = point
    return lon * math.pi / 180 * 10000, math.log(math.tan(math.pi / 4 + lat * math.pi / 360)) * 10000


def ranges(numbers):
    numbers = sorted(set(numbers))
    result = []
    a = b = numbers[0]
    for n in numbers[1:]:
        if n == b + 1:
            b = n
        else:
            result.append(str(a) if a == b else f'{a}-{b}')
            a = b = n
    result.append(str(a) if a == b else f'{a}-{b}')
    return ', '.join(result)


def usable_point(stop):
    return isinstance(stop.get('lat'), (int, float)) and isinstance(stop.get('lon'), (int, float))


def geometry_lines(geometry):
    if not geometry:
        return []
    if geometry.get('type') == 'LineString':
        return [geometry.get('coordinates', [])]
    if geometry.get('type') == 'MultiLineString':
        return geometry.get('coordinates', [])
    return []


def load_volume(folder, legacy=False):
    data = json.loads((folder / 'data.json').read_text())
    records = []
    for pattern in data.get('historic_patterns', []):
        p = dict(pattern)
        p['_kind'] = 'manual'
        p['_group'] = 'manual:' + p.get('date', 'Undated')
        p['_group_label'] = f'{clean(p.get("date", "Undated"))} | Historical reconstruction'
        p['_order'] = date_key(p.get('date', ''))
        records.append(p)
    for meta in data.get('snapshots', []):
        dataset = json.loads((folder / 'snapshots' / (meta['id'] + '.json')).read_text())
        for pattern in dataset['patterns']:
            p = dict(pattern)
            p['_kind'] = 'gtfs'
            p['_group'] = 'feed:' + meta['id']
            p['_group_label'] = f'{pretty_date(meta["id"])} | Original GO feed snapshot'
            p['_order'] = date_key(meta['id'])
            p['_snapshot'] = dataset['snapshot']
            p['sources'] = [dataset['snapshot']['url']]
            records.append(p)
    records.sort(key=lambda p: (p['_order'], p['_group'], str(p.get('branch', '')), str(p.get('direction_id', p.get('direction', ''))), p.get('first_service_date', ''), p.get('headsign', p.get('label', '')), p['id']))
    source_items = {}
    def add_source(value):
        item = {'url': value, 'title': value} if isinstance(value, str) else dict(value)
        url = item.get('url')
        if url and (url not in source_items or source_items[url].get('title') == url):
            source_items[url] = item
    for s in data.get('sources', []):
        add_source(s)
    for event in data.get('timeline', []):
        for u in event.get('sources', []):
            add_source(u)
    for p in records:
        for u in p.get('sources', []):
            add_source(u)
        for s in p['stops']:
            if s.get('location_source'):
                add_source({'url': s['location_source'], 'title': 'Stop-location reference: '+s['location_source']})
    source_list = list(source_items.values())
    source_ids = {s['url']: i + 1 for i, s in enumerate(source_list)}
    return {'data': data, 'folder': folder, 'legacy': legacy, 'patterns': records, 'sources': source_list, 'source_ids': source_ids}


class Volume:
    def __init__(self, model, land, output, known=None, final=False):
        self.model, self.land, self.output = model, land, output
        self.data = model['data']
        self.patterns = model['patterns']
        self.route = self.data['route']
        self.legacy = model['legacy']
        self.known = known or {}
        self.final = final
        self.c = canvas.Canvas(output, pagesize=letter, pageCompression=1, invariant=1)
        self.c.setTitle((self.data['name'] if self.legacy else f'GO {self.route}: {self.data["name"]}')+' - Route history atlas')
        self.c.setAuthor('GO Bus History Maps')
        self.c.setSubject('Source-backed route maps, chronology and complete documented stop sequences')
        self.c.setCreator('GO Bus History Maps - scripts/build_pdfs.py')
        self.page = 0
        self.positions = {}
        self.y = 0
        self.running = ''
        self.audit = {'patterns': [], 'stops': 0, 'unlocated': 0, 'map_labels': 0}
        self.form_ready = False
        self.entries = self.contents_entries()

    def style(self, size=10.4, leading=None, bold=False, color=INK):
        return ParagraphStyle('p', fontName='DejaVu-Bold' if bold else 'DejaVu', fontSize=size, leading=leading or size*1.4, textColor=color, alignment=TA_LEFT, spaceBefore=0, spaceAfter=0, splitLongWords=True, allowWidows=0, allowOrphans=0)

    def paragraph(self, text, x=None, y=None, width=None, size=10.4, leading=None, bold=False, color=INK, markup=False):
        x = M if x is None else x
        y = self.y if y is None else y
        width = CW if width is None else width
        p = Paragraph(text if markup else esc(text), self.style(size, leading, bold, color))
        _, h = p.wrap(width, H)
        p.drawOn(self.c, x, y-h)
        return h

    def para_height(self, text, width=CW, size=10.4, leading=None, bold=False, markup=False):
        return Paragraph(text if markup else esc(text), self.style(size, leading, bold)).wrap(width, H)[1]

    def text(self, text, x, y, size=10.4, bold=False, color=INK):
        self.c.setFillColor(color)
        self.c.setFont('DejaVu-Bold' if bold else 'DejaVu', size)
        self.c.drawString(x, y, clean(text))

    def new_page(self, running='', cover=False):
        if self.page:
            self.c.showPage()
        self.page += 1
        self.running = running
        self.c.setFillColor(PAPER)
        self.c.rect(0, 0, W, H, fill=1, stroke=0)
        if not cover:
            self.text('GO BUS HISTORY MAPS', M, H-27, 8.4, True, GREEN)
            short = self.data['name'] if self.legacy else f'ROUTE {self.route}'
            self.c.setFont('DejaVu', 8.4)
            self.c.setFillColor(MUTED)
            self.c.drawRightString(W-M, H-27, clean(short)[:65])
            self.c.setStrokeColor(BORDER)
            self.c.setLineWidth(.6)
            self.c.line(M, H-34, W-M, H-34)
        self.text('Evidence archive | 23 October 2026', M, 22, 8.1, False, MUTED)
        total = self.known.get('_pages')
        self.c.setFont('DejaVu', 8.5)
        self.c.setFillColor(MUTED)
        self.c.drawRightString(W-M, 22, f'{self.page} / {total}' if total else str(self.page))
        self.y = H-53

    def anchor(self, key, title, level=0):
        self.positions[key] = self.page
        self.c.bookmarkPage(key)
        self.c.addOutlineEntry(clean(title)[:180], key, level=level, closed=(level==0 and key.startswith('group:')))

    def ensure(self, needed, running=None):
        if self.y-needed < 53:
            self.new_page(running or self.running)
            if self.running:
                self.y -= self.paragraph(self.running+' - continued', size=16, leading=20, bold=True)+16

    def refs(self, urls):
        return ' '.join(f'<link href="#source-{self.model["source_ids"][u]}" color="#20664f">[S{self.model["source_ids"][u]}]</link>' for u in urls if u in self.model['source_ids'])

    def make_land_form(self):
        if self.form_ready:
            return
        self.c.beginForm('OntarioBase', -16000, 6000, -12000, 11000)
        self.c.setFillColor(LAND)
        self.c.setStrokeColor(BORDER)
        self.c.setLineWidth(0)
        for feature in self.land['features']:
            g = feature['geometry']
            polygons = [g['coordinates']] if g['type']=='Polygon' else g['coordinates'] if g['type']=='MultiPolygon' else []
            for rings in polygons:
                path = self.c.beginPath()
                for ring in rings:
                    for i, point in enumerate(ring):
                        x, y = projected(point)
                        if i == 0:
                            path.moveTo(x, y)
                        else:
                            path.lineTo(x, y)
                    path.close()
                self.c.drawPath(path, fill=1, stroke=1, fillMode=0)
        self.c.endForm()
        self.form_ready = True

    def diagram(self, pattern, x, y, width, height):
        """Fallback is explicitly a diagram; every numbered stop remains present."""
        c = self.c
        c.setFillColor(PALE)
        c.roundRect(x, y, width, height, 7, fill=1, stroke=0)
        self.text('STOP-ORDER DIAGRAM', x+14, y+height-22, 9.4, True, GREEN)
        n = len(pattern['stops'])
        cols = min(8, max(2, math.ceil(math.sqrt(n*2))))
        rows = math.ceil(n/cols)
        sx = (width-52)/(cols-1) if cols>1 else 0
        sy = min(42, (height-74)/max(1, rows-1))
        top = y+height-55
        pts = []
        for i in range(n):
            row, col = divmod(i, cols)
            if row%2:
                col = cols-1-col
            pts.append((x+26+col*sx, top-row*sy))
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.2)
        c.setDash(3,3)
        for a,b in zip(pts,pts[1:]):
            c.line(*a,*b)
        c.setDash()
        for i,(px,py) in enumerate(pts,1):
            c.setFillColor(PAPER)
            c.circle(px,py,10,fill=1,stroke=1)
            c.setFillColor(GREEN)
            c.setFont('DejaVu-Bold',9)
            c.drawCentredString(px,py-3.2,str(i))
        self.text('Numbers follow the complete ordered list below. Geography is not implied.',x+14,y+12,8.7,False,MUTED)
        return n

    def draw_map(self, pattern, x, y, width, height, audit=True):
        located = [(i+1,s) for i,s in enumerate(pattern['stops']) if usable_point(s)]
        lines = geometry_lines(pattern.get('geometry'))
        points = [p for line in lines for p in line]
        points += [[s['lon'],s['lat']] for _,s in located]
        if len(located)<2 or not points:
            result = self.diagram(pattern,x,y,width,height)
            if audit:
                self.audit['map_labels'] += result
            return
        self.make_land_form()
        c = self.c
        c.saveState()
        clip = c.beginPath()
        clip.roundRect(x,y,width,height,7)
        c.clipPath(clip,stroke=0,fill=0)
        c.setFillColor(WATER)
        c.rect(x,y,width,height,fill=1,stroke=0)
        projected_points = [projected(p) for p in points]
        xmin,xmax = min(p[0] for p in projected_points),max(p[0] for p in projected_points)
        ymin,ymax = min(p[1] for p in projected_points),max(p[1] for p in projected_points)
        scale = min((width-74)/max(xmax-xmin,1.7),(height-62)/max(ymax-ymin,1.2))
        cx,cy = (xmin+xmax)/2,(ymin+ymax)/2
        tx,ty = x+width/2-scale*cx,y+height/2-scale*cy
        def xy(point):
            px,py = projected(point)
            return tx+scale*px,ty+scale*py
        c.saveState()
        c.transform(scale,0,0,scale,tx,ty)
        c.doForm('OntarioBase')
        c.restoreState()
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.8)
        kind = pattern.get('geometry_kind','')
        if 'connections' in kind or kind=='schematic':
            c.setDash(4,3)
        for line in lines:
            if len(line)<2:
                continue
            path=c.beginPath()
            for i,p in enumerate(line):
                px,py=xy(p)
                if i: path.lineTo(px,py)
                else:path.moveTo(px,py)
            c.drawPath(path,fill=0,stroke=1)
        c.setDash()
        clusters=[]
        for number,s in located:
            px,py=xy([s['lon'],s['lat']])
            closest=next((g for g in clusters if math.hypot(px-g['x'],py-g['y'])<11),None)
            if closest is None:
                closest={'x':px,'y':py,'numbers':[],'points':[]};clusters.append(closest)
            closest['numbers'].append(number)
            closest['points'].append((px,py))
        for g in clusters:
            g['x']=sum(p[0] for p in g['points'])/len(g['points'])
            g['y']=sum(p[1] for p in g['points'])/len(g['points'])
        # Markers sit beneath the callout boxes so dense stop areas never
        # overwrite a label's digits. Leaders still identify each cluster.
        for _,s in located:
            px,py=xy([s['lon'],s['lat']])
            c.setFillColor(PAPER);c.setStrokeColor(GREEN);c.setLineWidth(1)
            c.circle(px,py,2.6,fill=1,stroke=1)
        # Place compact callout boxes in free space; close stops use number ranges.
        occupied=[]
        c.setFont('DejaVu-Bold',9.1)
        for g in sorted(clusters,key=lambda q:(-len(q['numbers']),min(q['numbers']))):
            label=ranges(g['numbers'])
            tw=pdfmetrics.stringWidth(label,'DejaVu-Bold',9.1)+8
            th=14
            best=None
            for radius in (9,17,27,40,56,75,98):
                for angle in (45,135,-45,-135,0,180,90,-90):
                    a=math.radians(angle)
                    bx=g['x']+math.cos(a)*radius-(tw if math.cos(a)<0 else 0)
                    by=g['y']+math.sin(a)*radius-(th if math.sin(a)<0 else 0)
                    if bx<x+5 or bx+tw>x+width-5 or by<y+18 or by+th>y+height-7:
                        continue
                    box=(bx,by,bx+tw,by+th)
                    overlap=sum(max(0,min(box[2],o[2])-max(box[0],o[0]))*max(0,min(box[3],o[3])-max(box[1],o[1])) for o in occupied)
                    penalty=overlap*1000+radius
                    if best is None or penalty<best[0]:best=(penalty,box)
                    if overlap==0:break
                if best and best[0]<1000:break
            if best is None:
                bx=min(max(g['x']+7,x+5),x+width-tw-5);by=min(max(g['y']+7,y+18),y+height-th-5);box=(bx,by,bx+tw,by+th)
            else:box=best[1]
            occupied.append((box[0]-2,box[1]-2,box[2]+2,box[3]+2))
            bx,by=box[:2]
            c.setStrokeColor(GREEN)
            c.setLineWidth(.55)
            ex=min(max(g['x'],bx),bx+tw);ey=min(max(g['y'],by),by+th)
            c.line(g['x'],g['y'],ex,ey)
            c.setFillColor(PAPER)
            c.roundRect(bx,by,tw,th,3,fill=1,stroke=0)
            c.setFillColor(GREEN)
            c.setFont('DejaVu-Bold',9.1)
            c.drawString(bx+4,by+3.2,label)
        # Quiet orientation and scale references in the frame corners.
        c.setFillColor(INK);c.setFont('DejaVu-Bold',8.7)
        c.drawCentredString(x+width-16,y+height-17,'N')
        c.setStrokeColor(INK);c.setLineWidth(.7)
        c.line(x+width-16,y+height-38,x+width-16,y+height-23)
        path=c.beginPath();path.moveTo(x+width-19,y+height-27);path.lineTo(x+width-16,y+height-21);path.lineTo(x+width-13,y+height-27);c.drawPath(path,fill=1,stroke=0)
        meanlat=sum(s['lat'] for _,s in located)/len(located)
        km_per_pt=(math.cos(math.radians(meanlat))*6371/10000)/scale
        target=70*km_per_pt
        choices=[v*10**e for e in range(-3,5) for v in (1,2,5)]
        km=max((v for v in choices if v<=target),default=.1)
        bar=km/km_per_pt
        c.setLineWidth(1);c.line(x+12,y+15,x+12+bar,y+15)
        c.line(x+12,y+12,x+12,y+18);c.line(x+12+bar,y+12,x+12+bar,y+18)
        c.setFont('DejaVu',8);c.drawString(x+12,y+22,f'{km:g} km')
        c.restoreState()
        c.setStrokeColor(BORDER);c.setLineWidth(.6);c.roundRect(x,y,width,height,7,fill=0,stroke=1)
        if audit:self.audit['map_labels']+=len(located)

    def contents_entries(self):
        entries=[{'key':'history','title':'Route history and evidence notes','level':0}]
        seen=set()
        for i,p in enumerate(self.patterns,1):
            if p['_group'] not in seen:
                entries.append({'key':'group:'+p['_group'],'title':p['_group_label'],'level':0});seen.add(p['_group'])
            title=f'{i:02d}  {p.get("branch",self.route)} | {p.get("label",p.get("headsign",p["id"]))}'
            if p.get('direction'):
                title+=' | '+p['direction']
            elif p.get('direction_id') not in (None,''):
                title+=' | dir. '+str(p['direction_id'])
            entries.append({'key':'pattern:'+p['id'],'title':title,'level':1})
        entries.append({'key':'sources','title':'Sources and attribution','level':0})
        return entries

    def cover(self):
        self.new_page(cover=True)
        self.anchor('overview','Overview',0)
        self.text('GO BUS HISTORY MAPS',M,H-45,10.5,True,GREEN)
        self.text('ROUTE HISTORY ATLAS',M,H-66,9,False,MUTED)
        self.y=H-99
        if not self.legacy:
            self.text(self.route,M,self.y-41,52,True,GREEN)
            title_x=M+99
            title_w=CW-99
            title_h=self.paragraph(self.data['name'],x=title_x,y=self.y,width=title_w,size=23,leading=29,bold=True)
            self.y-=max(61,title_h)+17
        else:
            self.y-=self.paragraph(self.data['name'],size=27,leading=33,bold=True)+18
        self.y-=self.paragraph(self.data.get('description',''),size=11,leading=16)+16
        years=sorted({p['_order'][0] for p in self.patterns if p['_order'][0]<9999})
        span=f'{years[0]} - {years[-1]}' if years and years[0]!=years[-1] else str(years[0]) if years else 'Dated evidence'
        stats=[(str(len(self.patterns)),'documented patterns'),(span,'evidence years'),(f'{sum(len(p["stops"]) for p in self.patterns):,}','listed stop occurrences')]
        bw=(CW-20)/3
        for i,(number,label) in enumerate(stats):
            bx=M+i*(bw+10)
            self.c.setFillColor(PALE);self.c.roundRect(bx,self.y-57,bw,57,6,fill=1,stroke=0)
            self.text(number,bx+12,self.y-24,18,True,GREEN)
            self.text(label,bx+12,self.y-43,8.6,False,MUTED)
        self.y-=76
        if self.patterns:
            current=[p for p in self.patterns if p.get('_snapshot',{}).get('id')=='2026-10-23']
            candidates=[p for p in current if p.get('branch')==self.route] or current or self.patterns
            representative=max(candidates,key=lambda p:len(p['stops']))
            height=min(267,self.y-128)
            self.draw_map(representative,M,self.y-height,CW,height,audit=False)
            self.y-=height+9
            caption=f'Illustrated pattern: {representative.get("branch",self.route)} | '+representative.get('label',representative.get('headsign',''))
            if representative['_kind']=='gtfs':
                caption+=' | Scheduled '+date_range(representative['first_service_date'],representative['last_service_date'])+'; feed captured '+pretty_date(representative['_snapshot']['id'])
            else:
                caption+=' | Documented '+clean(representative.get('date','See source'))
            self.y-=self.paragraph(caption,size=9.2,leading=12,color=MUTED)+12
        self.paragraph('A dated documentary atlas. Every pattern has its own numbered map and complete documented stop list. Reconstructed major-stop lists and full scheduled GTFS stop lists are identified separately.',y=self.y,size=10.1,leading=14,color=MUTED)

    def contents(self):
        self.new_page('Contents')
        self.anchor('contents','Contents',0)
        self.y-=self.paragraph('Contents',size=25,leading=30,bold=True)+9
        self.y-=self.paragraph('Use the clickable entries or PDF bookmarks to jump to a date, branch or direction. Pattern counts include separate directions, stopping patterns and boarding restrictions.',size=10.4,leading=15,color=MUTED)+16
        for entry in self.entries:
            is_group=entry['level']==0
            indent=0 if is_group else 12
            size=10.4 if is_group else 10.0
            text=entry['title']
            ph=self.para_height(text,width=CW-indent-44,size=size,leading=13.5,bold=is_group)
            self.ensure(ph+(12 if is_group else 6),'Contents')
            if is_group:self.y-=6
            h=self.paragraph(text,x=M+indent,y=self.y,width=CW-indent-44,size=size,leading=13.5,bold=is_group,color=GREEN if is_group else INK)
            page=self.known.get(entry['key'])
            self.c.setFillColor(MUTED);self.c.setFont('DejaVu-Bold' if is_group else 'DejaVu',10)
            self.c.drawRightString(W-M,self.y-10,str(page) if page else '-')
            self.c.linkRect('',entry['key'],(M,self.y-h-2,W-M,self.y+2),relative=0,thickness=0)
            self.y-=h+4

    def history(self):
        self.new_page('Route history')
        self.anchor('history','Route history and evidence notes',0)
        self.y-=self.paragraph('Route history',size=25,leading=30,bold=True)+9
        self.y-=self.paragraph('A snapshot proves what was published at that date. It does not by itself establish when a route began or ended. Reused route numbers and changing branch suffixes remain separate dated records.',size=10.4,leading=15,color=MUTED)+18
        for event in self.data.get('timeline',[]):
            body=esc(event['event'])+' '+self.refs(event.get('sources',[]))
            ph=self.para_height(body,width=CW-19,size=10.6,leading=15.5,markup=True)
            self.ensure(ph+41,'Route history')
            self.c.setStrokeColor(BORDER);self.c.setLineWidth(1.1);self.c.line(M+3,self.y-8,M+3,self.y-ph-28)
            self.c.setFillColor(GREEN);self.c.circle(M+3,self.y-7,3,fill=1,stroke=0)
            self.text(event['date'],M+18,self.y-10,10.4,True,GREEN)
            self.y-=23
            self.y-=self.paragraph(body,x=M+18,width=CW-18,size=10.6,leading=15.5,markup=True)+19
        self.ensure(100,'Evidence notes')
        self.y-=self.paragraph('Reading the maps',size=17,leading=22,bold=True)+10
        notes=[
            'Original GO feed: all scheduled stops are retained in their source order, including no-pickup and no-drop-off restrictions. The exact service dates are printed with the pattern.',
            'Historical reconstruction: the list generally contains published timing points or major stops. It is complete for that documented reconstruction, and may omit intermediate roadside stops.',
            'Solid lines use supplied feed shapes or an explicitly labelled corridor reconstruction. Dashed lines connect stop areas schematically. Number ranges mark close or co-located stops.',
            'Reference coordinates do not prove an old platform location. Stops without established coordinates remain in the ordered list; a stop-order diagram is used when a geographic map cannot be drawn.'
        ]+self.data.get('gaps',[])
        for note in notes:
            ph=self.para_height(note,width=CW-16,size=10.2,leading=14.7)
            self.ensure(ph+12,'Evidence notes')
            self.text('-',M,self.y-10,10.2,False,GREEN)
            self.y-=self.paragraph(note,x=M+15,width=CW-15,size=10.2,leading=14.7)+9

    def pattern_header(self,p,index,continued=False):
        self.new_page('Pattern '+str(index))
        kind='ORIGINAL GO FEED' if p['_kind']=='gtfs' else 'HISTORICAL RECONSTRUCTION'
        self.text(f'{kind} | PATTERN {index:02d} OF {len(self.patterns)}',M,self.y-7,8.9,True,GREEN)
        self.y-=24
        title=f'{p.get("branch",self.route)} | '+p.get('label',p.get('headsign',p['id']))
        if continued:title+=' - stops continued'
        self.y-=self.paragraph(title,size=18,leading=23,bold=True)+8
        if p['_kind']=='gtfs':
            subtitle='Scheduled: '+date_range(p['first_service_date'],p['last_service_date'])+f' | Direction ID {p.get("direction_id", "unspecified")} (source value)'
        else:
            subtitle=f'Documented: {p.get("date","See source")} | Direction: {p.get("direction","as listed")}'
        self.y-=self.paragraph(subtitle,size=10.2,leading=14.4,color=MUTED)+9
        return title

    def stop_note(self,s):
        notes=[]
        if not usable_point(s):notes.append('Location not established')
        pickup,drop=s.get('pickup_type'),s.get('drop_off_type')
        if pickup=='1':notes.append('No pickup')
        if drop=='1':notes.append('No drop-off')
        if pickup=='2' or drop=='2':notes.append('Advance arrangement')
        if pickup=='3' or drop=='3':notes.append('Coordinate with driver')
        return ' | '.join(notes)

    def draw_stop_columns(self,p,start,top,bottom=72):
        gap=23
        colw=(CW-gap)/2
        index=start
        lowest=top
        for col in range(2):
            y=top
            x=M+col*(colw+gap)
            while index<len(p['stops']):
                s=p['stops'][index]
                name=esc(s['name'])
                note=self.stop_note(s)
                if note:name+=f'<br/><font size="9.1" color="#91662f">{esc(note)}</font>'
                textw=colw-29
                para=Paragraph(name,self.style(10.4,14.1))
                _,ph=para.wrap(textw,H)
                rowh=max(17,ph)+7
                if y-rowh<bottom:break
                self.c.setFillColor(AMBER_PALE if not usable_point(s) else PALE)
                self.c.circle(x+9,y-8,9.2,fill=1,stroke=0)
                self.c.setFillColor(AMBER if not usable_point(s) else GREEN)
                self.c.setFont('DejaVu-Bold',8.6)
                self.c.drawCentredString(x+9,y-11,str(index+1))
                para.drawOn(self.c,x+27,y-ph)
                y-=rowh
                index+=1
                self.audit['stops']+=1
                if not usable_point(s):self.audit['unlocated']+=1
            lowest=min(lowest,y)
            if index>=len(p['stops']):break
        return index,lowest

    def pattern(self,p,index,group_new=False):
        self.pattern_header(p,index)
        if group_new:self.anchor('group:'+p['_group'],p['_group_label'],0)
        self.anchor('pattern:'+p['id'],f'{index:02d}. {p.get("branch",self.route)} | '+p.get('label',p.get('headsign','')),1)
        self.audit['patterns'].append(p['id'])
        scope='COMPLETE SCHEDULED STOP LIST' if p['_kind']=='gtfs' else 'DOCUMENTED MAJOR STOPS / TIMING POINTS'
        self.c.setFillColor(PALE if p['_kind']=='gtfs' else AMBER_PALE)
        self.c.roundRect(M,self.y-23,CW,23,5,fill=1,stroke=0)
        self.text(scope,M+9,self.y-15,8.8,True,GREEN if p['_kind']=='gtfs' else AMBER)
        self.c.setFillColor(MUTED);self.c.setFont('DejaVu',8.7)
        self.c.drawRightString(W-M-9,self.y-15,f'{len(p["stops"])} stops')
        self.y-=34
        source_line='Sources: '+self.refs(p.get('sources',[]))
        if p['_kind']=='gtfs':source_line+=' | Feed captured '+esc(p['_snapshot']['id'])
        self.y-=self.paragraph(source_line,size=9.2,leading=12.3,color=MUTED,markup=True)+8
        map_h=257
        self.draw_map(p,M,self.y-map_h,CW,map_h)
        self.y-=map_h+9
        kind=p.get('geometry_kind','')
        if p['_kind']=='manual' and 'connections' not in kind and kind!='schematic':
            note='Reconstructed corridor; local approaches may be generalized.'
        elif 'connections' in kind or kind=='schematic':
            note='Dashed line: schematic stop connections, not a street-by-street alignment.'
        else:
            note='Supplied GO shape, simplified for display'+('; clipped to this pattern’s endpoints.' if 'clipped' in kind else '.')
        missing=sum(not usable_point(s) for s in p['stops'])
        if missing:note+=f' {missing} stop location(s) remain unestablished; see the complete list.'
        if p['_kind']=='manual':note+=' Stop areas do not establish exact historical platforms.'
        self.y-=self.paragraph(note,size=9.2,leading=12.4,color=MUTED)+8
        if p.get('service_dates'):
            exact='<b>Exact operating dates in this feed:</b> '+esc(exact_dates(p['service_dates']))
            self.y-=self.paragraph(exact,size=8.9,leading=11.9,color=MUTED,markup=True)+10
        else:
            notes=p.get('notes','')
            if notes and len(notes)<500:
                self.y-=self.paragraph(notes,size=9.2,leading=12.4,color=MUTED)+9
        self.y-=self.paragraph('Ordered stops',size=12.5,leading=17,bold=True)+7
        start=0
        while start<len(p['stops']):
            before=start
            start,self.y=self.draw_stop_columns(p,start,self.y)
            if start<len(p['stops']):
                self.pattern_header(p,index,continued=True)
                self.y-=self.paragraph(f'Stop {start+1} onward | Numbers continue from the map on page {self.positions["pattern:"+p["id"]]}.',size=10.2,leading=14.5,color=MUTED)+18
            if start==before and self.y<100:
                raise RuntimeError('Insufficient room for any stop: '+p['id'])

    def sources(self):
        self.new_page('Sources and attribution')
        self.anchor('sources','Sources and attribution',0)
        self.y-=self.paragraph('Sources and attribution',size=24,leading=30,bold=True)+10
        self.y-=self.paragraph('Each [S] reference is clickable. Original timetables establish the printed timing points; GTFS archives establish the published scheduled patterns and coordinates. A catalog link or a later location reference does not prove continuous historical operation.',size=10.4,leading=15,color=MUTED)+18
        for i,s in enumerate(self.model['sources'],1):
            title=s.get('title',s['url'])
            if title==s['url'] or title.startswith('Stop-location reference:'):
                title='Stop-location or original-data reference' if title.startswith('Stop-location reference:') else 'Original linked source'
            url=s['url']
            markup=f'<b>[S{i}] {esc(title)}</b><br/><link href="{esc(url)}" color="#20664f">{esc(url)}</link>'
            ph=self.para_height(markup,width=CW,size=10.0,leading=14.0,markup=True)
            self.ensure(ph+16,'Sources and attribution')
            self.c.bookmarkPage('source-'+str(i))
            self.y-=self.paragraph(markup,size=10.0,leading=14.0,markup=True)+15
        self.ensure(170,'Attribution')
        self.y-=self.paragraph('About this volume',size=16,leading=21,bold=True)+10
        attribution='Data used in this product or service is provided with the permission of Metrolinx. Metrolinx makes no representations or warranties of any kind, express or implied, with respect to the Data and assumes no responsibility for the accuracy or currency of the data used in this product or service.'
        self.y-=self.paragraph(attribution,size=9.8,leading=14,color=MUTED)+12
        self.y-=self.paragraph('Basemap: Ontario Ministry of Natural Resources, Open Government Licence - Ontario. Modern municipal geography is a reference background, not a map of historical municipal boundaries. This independent archive is not a live trip planner.',size=9.8,leading=14,color=MUTED)+12
        repo='https://github.com/Ding-Ding-Projects/go-bus-history-maps'
        self.paragraph('Repository, interactive maps, original evidence links and CSV stop lists:<br/><link href="'+repo+'" color="#20664f">'+repo+'</link>',size=10.0,leading=14,markup=True)

    def build(self):
        self.cover()
        self.contents()
        self.history()
        seen=set()
        for i,p in enumerate(self.patterns,1):
            self.pattern(p,i,p['_group'] not in seen)
            seen.add(p['_group'])
        self.sources()
        self.positions['_pages']=self.page
        self.c.save()
        assert len(self.audit['patterns'])==len(self.patterns)
        assert len(set(self.audit['patterns']))==len(self.patterns)
        assert self.audit['stops']==sum(len(p['stops']) for p in self.patterns)
        return self.positions,self.audit


def build_one(model,land):
    route=model['data']['route']
    filename=f'{route}-history.pdf' if model['legacy'] else f'route-{route.zfill(2)}-history.pdf'
    dest=model['folder']/filename
    # Two deterministic passes: contents and page totals are exact on pass two.
    first=io.BytesIO()
    positions,_=Volume(model,land,first).build()
    final_positions,audit=Volume(model,land,str(dest),positions,True).build()
    if positions!=final_positions:
        raise RuntimeError('Pagination changed between passes: '+route)
    reader=PdfReader(dest)
    if len(reader.pages)!=positions['_pages']:
        raise RuntimeError('PDF page count mismatch: '+route)
    return {'route':route,'legacy':model['legacy'],'path':str(dest.relative_to(ROOT)),'pages':len(reader.pages),'patterns':len(model['patterns']),'stop_count':audit['stops'],'unlocated_stop_count':audit['unlocated'],'bytes':dest.stat().st_size,'pattern_pages':{k[8:]:v for k,v in positions.items() if k.startswith('pattern:')}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes',nargs='*',help='Numeric route numbers to build; omit to build all unless --legacy is supplied alone')
    parser.add_argument('--legacy',nargs='*',help='Legacy corridor IDs to build')
    parser.add_argument('--all',action='store_true',help='Build all numeric routes and legacy corridors')
    args=parser.parse_args()
    for name,file in [('DejaVu','DejaVuSans.ttf'),('DejaVu-Bold','DejaVuSans-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(name,str(FONT_ROOT/file)))
    pdfmetrics.registerFontFamily('DejaVu',normal='DejaVu',bold='DejaVu-Bold',italic='DejaVu',boldItalic='DejaVu-Bold')
    catalog=json.loads((ROOT/'data/catalog.json').read_text())
    land=json.loads((ROOT/'assets/ontario-mainland.geojson').read_text())
    all_requested=args.all or (args.routes is None and args.legacy is None)
    models=[]
    for row in catalog['routes']:
        if all_requested or args.routes is not None and str(row['route']) in args.routes:
            models.append(load_volume(ROOT/'routes'/row['folder']))
    for row in catalog.get('legacy',[]):
        if all_requested or args.legacy is not None and row['id'] in args.legacy:
            models.append(load_volume(ROOT/'legacy'/row['id'],True))
    if not models:raise SystemExit('No matching route or legacy volume requested')
    manifest_path=ROOT/'data/pdf-manifest.json'
    previous=json.loads(manifest_path.read_text()).get('files',[]) if manifest_path.exists() else []
    records={x['route']:x for x in previous}
    started=time.time()
    for model in models:
        record=build_one(model,land)
        records[record['route']]=record
        print(f"{record['route']}: {record['pages']} pages; {record['patterns']} patterns; {record['stop_count']} stops; {record['bytes']:,} bytes",flush=True)
    files=sorted(records.values(),key=lambda x:(x['legacy'],int(x['route']) if x['route'].isdigit() else x['route']))
    manifest={'schema_version':1,'as_of':catalog['as_of'],'files':files,'totals':{'files':len(files),'pages':sum(x['pages'] for x in files),'patterns':sum(x['patterns'] for x in files),'stop_count':sum(x['stop_count'] for x in files),'bytes':sum(x['bytes'] for x in files)},'notes':['Every documented pattern and ordered stop in the source route data is included.','Page numbers in pattern_pages are one-based.','Original feed service dates are printed exactly in compact day ranges; gaps remain explicit.','Historical reconstructions identify their major-stop scope and any unlocated stops.']}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('TOTALS '+json.dumps(manifest['totals'])+f' | elapsed {time.time()-started:.1f}s',flush=True)


if __name__=='__main__':main()
