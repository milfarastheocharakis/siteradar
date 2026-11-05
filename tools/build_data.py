#!/usr/bin/env python3
"""Build SiteRadar's business data files from an osmium GeoJSONSeq export of OpenStreetMap.

Usage: build_data.py <export.geojsonseq> <index.html> <out dir> <OpenStreetMap timestamp> [<overture.parquet> <Overture release>]

Writes, replacing what was there:
  <out>/index.json          the area covered, the data date, the cells and the municipalities
  <out>/cells/<a>_<o>.json  the businesses in each 0.02-degree cell, in the Overpass JSON shape the app reads
  <out>/munis/<id>.json     each municipality's boundary, in the Overpass "out geom" shape
  <out>/LICENSE.txt         where the data comes from and its licences (the Overture licence must travel with the data)

The kinds of places kept are read from the app itself (Q_AMENITY, Q_TOURISM, Q_LEISURE), so the
files hold exactly what the app's live map-data query would return. So are the rules that leave out places
that are not companies (NOT_COMPANY, STILL_COMPANY and NOT_COMPANY_SITES): public bodies, state schools,
churches, clubs, banks, ports.

Businesses that share a website with branches all over the area get "siteradar:chain" (the name most of
them use), so the app counts them as a chain even without a brand tag.

With an Overture Maps places file (see fetch_overture.py), its businesses are added too: those OpenStreetMap
already has give it their missing website, social pages and phone, and the rest are added as "overture" elements.
"""
import json
import math
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from overture import km, licence_text, name_key

CELL = 0.02                         # degrees; the app reads it from index.json
FACTOR = round(1 / CELL)
BBOX = (34.75, 23.45, 35.75, 26.35)  # south, west, north, east: Crete and Gavdos
SIMPLIFY = 0.0001                   # degrees (about 10 m) for municipality boundaries
# Only the tags the app reads, to keep the files small.
KEEP_TAG = re.compile(r'^(name(:en|:el)?|shop|amenity|tourism|office|craft|healthcare|leisure|cuisine|addr:.*|phone|mobile|email|website|url'
                      r'|facebook|instagram|contact:.*|brand(:wikidata|:en|:el)?|operator(:type)?|opening_hours|stars|rooms|description'
                      r'|disused|abandoned|overture:.*|siteradar:chain)$')
URL_TAGS = ('website', 'contact:website', 'url')
# Query parameters that only track where a click came from.
TRACKING = re.compile(r'^(utm_[a-z_]+|fbclid|gclid|dclid|gbraid|wbraid|msclkid|mc_cid|mc_eid|mcid|yclid|igshid|_ga|_gl|y_source|srsltid)$', re.I)
DIGITS = 5                          # decimals kept in coordinates: about 1 m


def app_lists(html):
    lists = {}
    for key in ('Q_AMENITY', 'Q_TOURISM', 'Q_LEISURE'):
        m = re.search(r"const %s = '([^']+)';" % key, html)
        if not m:
            sys.exit(f'{key} not found in the app')
        lists[key] = set(m.group(1).split('|'))
    for key in ('NOT_COMPANY', 'STILL_COMPANY', 'NOT_COMPANY_SITES'):
        m = re.search(r'const %s = (\[\n.*?\n\]);' % key, html, re.S)
        if not m:
            sys.exit(f'{key} not found in the app')
        lists[key] = json.loads(m.group(1))
    # The app matches these on whole words, like this.
    lists['not_company'] = re.compile(r'(?:^| )(?:%s)(?= |$)' % '|'.join(lists['NOT_COMPANY']))
    lists['still_company'] = re.compile(r'(?:^| )(?:%s)(?= |$)' % '|'.join(lists['STILL_COMPANY']))
    return lists


def name_words(name):
    """The name as the app matches it: lower case, no accents, ς as σ, other characters as single spaces."""
    s = unicodedata.normalize('NFD', str(name or ''))
    s = ''.join(c for c in s if not '\u0300' <= c <= '\u036f').lower().replace('ς', 'σ')
    return re.sub(r'[\W_]+', ' ', s).strip()


def host_of(url):
    url = str(url or '').strip()
    if not url:
        return ''
    if not re.match(r'^https?://', url, re.I):
        url = 'http://' + url.lstrip('/')
    try:
        host = (urlsplit(url).hostname or '').lower()
    except ValueError:
        return ''
    return host[4:] if host.startswith('www.') else host


def hosts_of(tags):
    return [h for k in URL_TAGS for v in str(tags.get(k) or '').split(';') for h in [host_of(v)] if h]


def not_company(tags, q):
    """True for a public body, state school, church, club, bank or port, by name or by website, as the app decides."""
    words = name_words(tags.get('name'))
    if q['not_company'].search(words) and not q['still_company'].search(words):
        return True
    return any(h == d or h.endswith('.' + d) for h in hosts_of(tags) for d in q['NOT_COMPANY_SITES'])


def clean_url(url):
    """The address without the parameters that only track clicks (utm_source and the like)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)]
    if len(kept) == len(parse_qsl(parts.query, keep_blank_values=True)):
        return url
    return urlunsplit(parts._replace(query=urlencode(kept)))


def point(el):
    return el.get('lat', el.get('center', {}).get('lat')), el.get('lon', el.get('center', {}).get('lon'))


def mark_chains(elements):
    """Mark the businesses that share a website with branches all over the area: at least three with the same name
    2 km or more apart, or two 20 km or more apart. Directories and booking sites list businesses with all different
    names, so they don't count. Returns {website host: chain name}."""
    by_host = defaultdict(list)
    for el in elements:
        hosts = hosts_of(el['tags'])
        if hosts:
            by_host[hosts[0]].append(el)
    chains = {}
    for host, els in by_host.items():
        if len(els) < 3:
            continue
        groups = defaultdict(list)
        for el in els:
            groups[name_key(el['tags'].get('name'))].append(el)
        same = max(groups.values(), key=len)
        if len(same) < 2 or len(same) < 0.3 * len(els):
            continue
        pts = [point(el) for el in same]
        spread = max(km(*a, *b) for i, a in enumerate(pts) for b in pts[i + 1:])
        if not ((len(same) >= 3 and spread >= 2) or spread >= 20):
            continue
        chains[host] = Counter(el['tags']['name'] for el in same).most_common(1)[0][0]
        for el in els:
            el['tags']['siteradar:chain'] = chains[host]
    return chains


def is_business(t, q):
    if not t.get('name'):
        return False
    return bool(t.get('shop') or t.get('office') or t.get('craft') or t.get('healthcare')
                or t.get('amenity') in q['Q_AMENITY'] or t.get('tourism') in q['Q_TOURISM']
                or t.get('leisure') in q['Q_LEISURE'])


def is_municipality(t):
    return t.get('boundary') == 'administrative' and str(t.get('name', '')).startswith('Δήμος')


def osm_ref(feature):
    """('node'|'way'|'relation', id) from osmium's @type/@id attributes or its type_id feature id."""
    p = feature.get('properties') or {}
    typ, oid = p.get('@type'), p.get('@id')
    if typ in ('node', 'way', 'relation') and oid is not None:
        return typ, int(oid)
    fid = str(feature.get('id', ''))
    m = re.match(r'^([nwra])(\d+)$', fid)
    if not m:
        return None
    letter, num = m.group(1), int(m.group(2))
    if letter == 'a':  # libosmium area ids: way id * 2, relation id * 2 + 1
        return ('relation', (num - 1) // 2) if num % 2 else ('way', num // 2)
    return {'n': 'node', 'w': 'way', 'r': 'relation'}[letter], num


def points(geom):
    t, c = geom.get('type'), geom.get('coordinates') or []
    if t == 'Point':
        return [c]
    if t in ('LineString', 'MultiPoint'):
        return c
    if t in ('Polygon', 'MultiLineString'):
        return [p for ring in c for p in ring]
    if t == 'MultiPolygon':
        return [p for poly in c for ring in poly for p in ring]
    return []


def centre(geom):
    """Centre of the bounding box, like Overpass 'out center'."""
    pts = points(geom)
    if not pts:
        return None
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2


def cell_of(lat, lon):
    return f'{math.floor(lat * FACTOR)}_{math.floor(lon * FACTOR)}'


def simplify(ring, tol):
    """Douglas-Peucker on a closed ring of [lon, lat]."""
    if len(ring) <= 4:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = ring[a]
        bx, by = ring[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = ring[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm if norm else math.hypot(px - ax, py - ay)
            if d > best:
                best, idx = d, i
        if idx > 0 and best > tol:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    out = [p for p, k in zip(ring, keep) if k]
    return out if len(out) >= 4 else ring


def trim_tags(tags):
    out = {k: v for k, v in tags.items() if KEEP_TAG.match(k)}
    if 'description' in out:
        out['description'] = str(out['description'])[:300]
    for k in URL_TAGS:
        if k in out:
            out[k] = ';'.join(clean_url(v.strip()) for v in str(out[k]).split(';'))
    return out


def write_elements(path, elements):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{"elements":[\n')
        f.write(',\n'.join(json.dumps(e, ensure_ascii=False, separators=(',', ':')) for e in elements))
        f.write('\n]}\n')


def main():
    if len(sys.argv) not in (5, 7):
        sys.exit(__doc__)
    src, html_path, out, osm_date = sys.argv[1:5]
    overture_file, overture_release = (sys.argv[5:7] + [None, None])[:2]
    q = app_lists(open(html_path, encoding='utf-8').read())
    south, west, north, east = BBOX

    businesses, munis = {}, {}
    with open(src, encoding='utf-8') as f:
        for line in f:
            line = line.strip().lstrip('\x1e')
            if not line:
                continue
            feature = json.loads(line)
            tags = {k: v for k, v in (feature.get('properties') or {}).items() if not k.startswith('@')}
            geom = feature.get('geometry') or {}
            ref = osm_ref(feature)
            if not ref:
                continue
            if is_municipality(tags) and geom.get('type') in ('Polygon', 'MultiPolygon'):
                polys = [geom['coordinates']] if geom['type'] == 'Polygon' else geom['coordinates']
                munis[ref[1]] = (tags, polys)
                continue
            if ref in businesses or not is_business(tags, q) or not_company(tags, q):
                continue
            c = centre(geom)
            if not c:
                continue
            lat, lon = round(c[0], DIGITS), round(c[1], DIGITS)
            if not (south <= lat <= north and west <= lon <= east):
                continue
            el = {'type': ref[0], 'id': ref[1]}
            if ref[0] == 'node':
                el['lat'], el['lon'] = lat, lon
            else:
                el['center'] = {'lat': lat, 'lon': lon}
            el['tags'] = trim_tags(tags)
            businesses[ref] = el

    overture_info = None
    if overture_file:
        import pyarrow.parquet as pq
        from overture import element_from, merge
        from overture import datasets_of
        found, datasets = [], set()
        for place in pq.read_table(overture_file).to_pylist():
            el = element_from(place, DIGITS)
            if el and south <= el['lat'] <= north and west <= el['lon'] <= east and is_business(el['tags'], q):
                el['tags'] = trim_tags(el['tags'])
                found.append(el)
                datasets |= datasets_of(place)
        if len(found) < int(os.environ.get('MIN_OVERTURE', '1000')):
            sys.exit(f'Only {len(found)} Overture businesses: has the Overture format changed? Refusing to publish')
        fresh, merged = merge(list(businesses.values()), found)
        for el in fresh:
            businesses[('overture', el['id'])] = el
        # Only now, so that an OpenStreetMap business whose Overture twin has a public website (gov.gr and the
        # like) takes that website and goes too, instead of staying behind as a business with no website.
        public = [ref for ref, el in businesses.items() if not_company(el['tags'], q)]
        for ref in public:
            del businesses[ref]
        added = sum(1 for ref in businesses if ref[0] == 'overture')
        overture_info = {'release': overture_release, 'kept': len(found), 'added': added, 'merged': merged}
        print(f'Overture {overture_release}: {len(found)} businesses, {merged} already in OpenStreetMap, {added} added; '
              f'{len(public)} left out as not companies ({sum(1 for ref in public if ref[0] != "overture")} from OpenStreetMap)')

    chains = mark_chains(list(businesses.values()))
    print(f'{len(chains)} websites shared by chains: {sum(1 for el in businesses.values() if "siteradar:chain" in el["tags"])} businesses marked')

    for sub in ('cells', 'munis'):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
        os.makedirs(os.path.join(out, sub))

    order = {'node': 0, 'way': 1, 'relation': 2, 'overture': 3}
    cells = {}
    for (typ, oid), el in sorted(businesses.items(), key=lambda kv: (order[kv[0][0]], str(kv[0][1]).zfill(20))):
        lat = el.get('lat', el.get('center', {}).get('lat'))
        lon = el.get('lon', el.get('center', {}).get('lon'))
        cells.setdefault(cell_of(lat, lon), []).append(el)
    for key, els in cells.items():
        write_elements(os.path.join(out, 'cells', f'{key}.json'), els)

    muni_index = []
    for rid, (tags, polys) in sorted(munis.items()):
        members, lats, lons = [], [], []
        for poly in polys:
            for k, ring in enumerate(poly):
                ring = simplify(ring, SIMPLIFY)
                members.append({'type': 'way', 'role': 'outer' if k == 0 else 'inner',
                                'geometry': [{'lat': round(p[1], 5), 'lon': round(p[0], 5)} for p in ring]})
                lats += [p[1] for p in ring]
                lons += [p[0] for p in ring]
        keep = {k: v for k, v in tags.items() if k in ('name', 'name:en', 'name:el', 'admin_level', 'boundary', 'ref')}
        write_elements(os.path.join(out, 'munis', f'{rid}.json'), [{'type': 'relation', 'id': rid, 'tags': keep, 'members': members}])
        muni_index.append({'id': rid, 'name': tags.get('name', ''), 'nameEn': tags.get('name:en', ''),
                           'adminLevel': tags.get('admin_level', ''),
                           'box': [round(min(lats), 5), round(min(lons), 5), round(max(lats), 5), round(max(lons), 5)]})

    index = {
        'v': 1,
        'osmDate': osm_date,
        'built': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'cell': CELL,
        'bbox': list(BBOX),
        'cells': {k: len(v) for k, v in sorted(cells.items())},
        'overture': overture_info,
        'munis': muni_index,
    }
    with open(os.path.join(out, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
        f.write('\n')
    with open(os.path.join(out, 'LICENSE.txt'), 'w', encoding='utf-8') as f:
        f.write(licence_text(overture_release, datasets) if overture_info else licence_text())
    print(f'{len(businesses)} businesses in {len(cells)} cells, {len(munis)} municipalities, OpenStreetMap {osm_date}')
    if len(businesses) < int(os.environ.get('MIN_BUSINESSES', '1000')) or not munis:
        sys.exit('Too little data: refusing to publish it')


if __name__ == '__main__':
    main()
