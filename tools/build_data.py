#!/usr/bin/env python3
"""Build SiteRadar's business data files from an osmium GeoJSONSeq export of OpenStreetMap.

Usage: build_data.py <export.geojsonseq> <index.html> <out dir> <OpenStreetMap timestamp>

Writes, replacing what was there:
  <out>/index.json          the area covered, the data date, the cells and the municipalities
  <out>/cells/<a>_<o>.json  the businesses in each 0.1-degree cell, in the Overpass JSON shape the app reads
  <out>/munis/<id>.json     each municipality's boundary, in the Overpass "out geom" shape

The kinds of places kept are read from the app itself (Q_AMENITY, Q_TOURISM, Q_LEISURE), so the
files hold exactly what the app's live map-data query would return.
"""
import json
import math
import os
import re
import shutil
import sys
from datetime import datetime, timezone

CELL = 0.1                          # degrees; the app uses the same size
BBOX = (34.75, 23.45, 35.75, 26.35)  # south, west, north, east: Crete and Gavdos
SIMPLIFY = 0.0001                   # degrees (about 10 m) for municipality boundaries
DROP_TAG = re.compile(r'^(source(:.*)?|note(:.*)?|fixme|FIXME|check_date(:.*)?|survey:date|mapillary|image|wikimedia_commons)$')
KEEP_NAMES = {'name', 'name:en', 'name:el'}


def app_lists(html):
    lists = {}
    for key in ('Q_AMENITY', 'Q_TOURISM', 'Q_LEISURE'):
        m = re.search(r"const %s = '([^']+)';" % key, html)
        if not m:
            sys.exit(f'{key} not found in the app')
        lists[key] = set(m.group(1).split('|'))
    return lists


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
    return f'{math.floor(lat * 10)}_{math.floor(lon * 10)}'


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
    out = {}
    for k, v in tags.items():
        if k.startswith('@') or DROP_TAG.match(k):
            continue
        if k.startswith('name:') and k not in KEEP_NAMES:
            continue
        out[k] = v
    return out


def write_elements(path, elements):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{"elements":[\n')
        f.write(',\n'.join(json.dumps(e, ensure_ascii=False, separators=(',', ':')) for e in elements))
        f.write('\n]}\n')


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    src, html_path, out, osm_date = sys.argv[1:]
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
            if ref in businesses or not is_business(tags, q):
                continue
            c = centre(geom)
            if not c:
                continue
            lat, lon = round(c[0], 7), round(c[1], 7)
            if not (south <= lat <= north and west <= lon <= east):
                continue
            el = {'type': ref[0], 'id': ref[1]}
            if ref[0] == 'node':
                el['lat'], el['lon'] = lat, lon
            else:
                el['center'] = {'lat': lat, 'lon': lon}
            el['tags'] = trim_tags(tags)
            businesses[ref] = el

    for sub in ('cells', 'munis'):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
        os.makedirs(os.path.join(out, sub))

    order = {'node': 0, 'way': 1, 'relation': 2}
    cells = {}
    for (typ, oid), el in sorted(businesses.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
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
        'munis': muni_index,
    }
    with open(os.path.join(out, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'{len(businesses)} businesses in {len(cells)} cells, {len(munis)} municipalities, OpenStreetMap {osm_date}')
    if len(businesses) < int(os.environ.get('MIN_BUSINESSES', '1000')) or not munis:
        sys.exit('Too little data: refusing to publish it')


if __name__ == '__main__':
    main()
