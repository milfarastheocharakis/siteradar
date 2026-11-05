#!/usr/bin/env python3
"""Download the Overture Maps places inside a bounding box from Overture's free public bucket.

Usage: fetch_overture.py <west,south,east,north> <out.parquet>
Prints the release it used (for example 2026-10-21.0) as its last line.
"""
import os
import re
import sys
import urllib.request

import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import pyarrow.parquet as pq

BUCKET = 'overturemaps-us-west-2'
COLUMNS = ['id', 'names', 'basic_category', 'taxonomy', 'websites', 'socials', 'emails', 'phones', 'brand',
           'addresses', 'confidence', 'operating_status', 'sources', 'bbox']


def latest_release():
    url = f'https://{BUCKET}.s3.us-west-2.amazonaws.com/?list-type=2&prefix=release/&delimiter=/'
    with urllib.request.urlopen(url, timeout=60) as r:
        xml = r.read().decode()
    releases = sorted(re.findall(r'<Prefix>release/(\d{4}-\d{2}-\d{2}\.\d+)/</Prefix>', xml))
    if not releases:
        sys.exit('No Overture release found')
    return releases[-1]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    west, south, east, north = map(float, sys.argv[1].split(','))
    release = latest_release()
    opts = {'anonymous': True, 'region': 'us-west-2'}
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    if proxy:  # inside a sandbox that reaches the internet through a proxy
        opts['proxy_options'] = proxy
        if os.path.exists('/root/.ccr/ca-bundle.crt'):
            opts['tls_ca_file_path'] = '/root/.ccr/ca-bundle.crt'
    fs = pafs.S3FileSystem(**opts)
    data = ds.dataset(f'{BUCKET}/release/{release}/theme=places/type=place/', filesystem=fs, format='parquet')
    names = set(data.schema.names)
    cols = [c for c in COLUMNS if c in names]
    where = ((pc.field('bbox', 'xmin') >= west) & (pc.field('bbox', 'xmin') <= east)
             & (pc.field('bbox', 'ymin') >= south) & (pc.field('bbox', 'ymin') <= north))
    table = data.to_table(columns=cols, filter=where)
    pq.write_table(table, sys.argv[2])
    print(f'{table.num_rows} places')
    print(release)


if __name__ == '__main__':
    main()
