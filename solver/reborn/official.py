"""Read only official card-search pages. Never read member decks or legality icons.

Only exact normalized pool matches or explicitly reviewed identity aliases are
persisted; no outside-pool cards enter search.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import re
import time
import urllib.request
from bs4 import BeautifulSoup
from .import_pool import ROOT, dump, key
from .verified_data import load_identity_aliases

BASE = 'https://www.db.yugioh-card.com/yugiohdb/card_search.action'
UPDATED_FROM_RE = re.compile(r'^(.*?)\s+\(Updated from:\s*(.*?)\)\s*$')


def split_official_display_name(display_name):
    """Return the current official name plus any explicit previous-name note.

    Neuron currently renders renamed cards as, for example,
    ``Slime Toad (Updated from: Frog the Jam)`` inside ``.card_name``.  The
    parenthetical is provenance, not part of the current card name.  Matching the
    whole display string creates false missing-text records for otherwise exact
    pool titles.  Strip only this exact official suffix; do not remove arbitrary
    parentheticals from card names.
    """
    display = ' '.join(str(display_name or '').split())
    match = UPDATED_FROM_RE.match(display)
    if not match:
        return display, None
    return match.group(1).strip(), match.group(2).strip()


def _load_identity_aliases():
    aliases, _ = load_identity_aliases()
    return aliases


def allowed_official_names(cards, aliases):
    """Names the official crawler may retain; aliases must be pre-reviewed."""
    out = {key(c['name']) for c in cards}
    for card in cards:
        spec = aliases.get(card['name'])
        if spec and spec.get('engine_name'):
            out.add(key(spec['engine_name']))
    return out


def resolve_official_record(card, matched, aliases):
    """Resolve exact current official record for one pool card."""
    direct = matched.get(key(card['name']))
    if direct is not None:
        return direct, 'exact_pool_title'
    spec = aliases.get(card['name'])
    if not spec:
        return None, None
    record = matched.get(key(spec.get('engine_name', '')))
    if record is None:
        return None, None
    source = 'reviewed_shared_identity_alias' if spec.get('allow_shared_engine_identity') else 'reviewed_identity_alias'
    return record, source


def parse_page(html, url, allowed):
    soup = BeautifulSoup(html, 'html.parser')
    records = []
    for row in soup.select('#card_list .t_row'):
        name_node = row.select_one('.card_name')
        if not name_node:
            continue
        display_name = name_node.get_text(' ', strip=True)
        name, updated_from = split_official_display_name(display_name)
        if key(name) not in allowed:
            continue
        spec_node = row.select_one('.box_card_spec')
        body_node = row.select_one('.box_card_text')
        cid_node = row.select_one('input.cid')
        attr_node = row.select_one('.box_card_attribute')
        if not (spec_node and body_node and cid_node and attr_node):
            continue
        spec = spec_node.get_text(' ', strip=True)
        body = body_node.get_text(' ', strip=True)
        cid = cid_node['value']
        attr = attr_node.get_text(' ', strip=True)
        extra = any(word in spec for word in ('Fusion', 'Synchro', 'Xyz', 'Link'))
        placement = 'extra' if extra else ('excluded' if 'Token' in spec else 'main')
        record = dict(
            name=name,
            official_display_name=display_name,
            cid=cid,
            spec=spec,
            attribute=attr,
            text=body,
            placement=placement,
            source_url=f'{BASE}?ope=2&cid={cid}&request_locale=en',
            retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            page_sha256=hashlib.sha256(html).hexdigest(),
            text_sha256=hashlib.sha256(body.encode()).hexdigest(),
            verification='official_current_text_retrieved',
            request_url=url,
        )
        if updated_from:
            record['updated_from'] = updated_from
        records.append(record)
    count = re.search(r'Search Results:\s*[\d,]+\s*-\s*[\d,]+\s*of\s*([\d,]+)', soup.get_text(' ',strip=True))
    return records, int(count[1].replace(',','')) if count else None


def fetch_page(page, allowed):
    url = f'{BASE}?ope=1&sess=1&rp=100&page={page}&request_locale=en'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=35) as response:
                html = response.read()
            records, total = parse_page(html, url, allowed)
            if total is None:
                raise ValueError('Missing official search count; refusing silent empty page')
            return dict(page=page, url=url, total=total, records=records)
        except Exception as exc:
            if attempt == 2:
                return dict(page=page, url=url, error=f'{type(exc).__name__}: {exc}')
            time.sleep(1+attempt)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    cards=json.loads((ROOT/'data/processed/cards.json').read_text())
    aliases=_load_identity_aliases()
    allowed=allowed_official_names(cards, aliases)
    cache=ROOT/'data/official_pages';cache.mkdir(exist_ok=True)
    first=fetch_page(1,allowed)
    if 'error' in first:
        raise RuntimeError(first)
    dump(cache/'001.json',first)
    total_pages=(first['total']+99)//100
    pending=[p for p in range(2,total_pages+1) if args.refresh or not (cache/f'{p:03d}.json').exists()
             or 'error' in json.loads((cache/f'{p:03d}.json').read_text())]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for result in executor.map(lambda p:fetch_page(p,allowed),pending):
            dump(cache/f"{result['page']:03d}.json",result)
            print(json.dumps({'page':result['page'],'matched':len(result.get('records',[])),
                              'error':result.get('error')}),flush=True)
    matched={}; conflicts=[];errors=[]
    for p in range(1,total_pages+1):
        batch=json.loads((cache/f'{p:03d}.json').read_text())
        if 'error' in batch:errors.append(batch)
        for record in batch.get('records',[]):
            k=key(record['name'])
            if k in matched and matched[k]['text_sha256']!=record['text_sha256']:
                conflicts.append(k)
            matched[k]=record
    alias_matches=[]
    for card in cards:
        record, source=resolve_official_record(card, matched, aliases)
        if record and key(record['name']) not in conflicts:
            stored=dict(record)
            stored['pool_identity_source']=source
            if source in {'reviewed_identity_alias','reviewed_shared_identity_alias'}:
                stored['pool_legacy_name']=card['name']
                alias_matches.append({
                    'pool_name':card['name'],
                    'official_current_name':record['name'],
                    'cid':record['cid'],
                    'identity_source':source,
                })
            card['official']=stored;card['placement']=stored['placement']
    dump(ROOT/'data/processed/cards.json',cards)
    dump(ROOT/'reports/text_coverage.json',dict(total=len(cards),matched=sum(bool(c['official']) for c in cards),
        reviewed_identity_alias_matches=alias_matches,
        missing=[c['name'] for c in cards if not c['official']],conflicts=conflicts,errors=errors,
        note=(
            'Latest official text snapshot. Official `(Updated from: ...)` display suffixes are retained as '
            'provenance but are not treated as part of the current card name. Reviewed identity aliases, including '
            'explicit same-card shared identities, may resolve a legacy pool title to its current official name; '
            'unreviewed fuzzy names are never accepted. Refresh and invalidate affected implementations before new promoted runs.'
        )))


if __name__=='__main__':main()
