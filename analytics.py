"""Independent per-store ETL and BI metrics; run with Python 3.10+."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import json, re
import pandas as pd
import yaml

BASE = Path(__file__).parent / 'data'

def clean_text(v):
    if pd.isna(v): return ''
    return ' '.join(str(v).strip().casefold().split())

def norm_phone(v): return re.sub(r'\D', '',clean_text(v))

def cents(v):
    """Parse USD/EUR price, including 29€50¢ / €29¢50, into USD cents."""
    if v is None or pd.isna(v): return None
    s = re.sub(r"\s+", "", str(v)).replace(",", "")
    if not s or s.casefold() in {"null", "nan", "none"}: return None
    eur = bool(re.search(r"€|EUR", s, re.I))
    usd = bool(re.search(r"\$|USD", s, re.I))
    if eur == usd: return None
    if '¢' in s:
        parts = re.findall(r"\d+", s)
        if len(parts) != 2 or len(parts[1]) > 2: return None
        amount = Decimal(parts[0]) + Decimal(parts[1])/100
    else:
        t = re.sub(r"(?i)EUR|USD|€|\$", "", s)
        if not re.fullmatch(r"\d+(?:\.\d+)?", t): return None
        amount = Decimal(t)
    amount *= Decimal('1.2') if eur else Decimal('1')
    if not amount.is_finite() or amount < 0: return None
    return int((amount*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

class DSU:
    def __init__(self,ids): self.p = {int(i):int(i) for i in ids}
    def find(self,x):
        x=int(x)
        while x != self.p[x]:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self,a,b):
        a,b=self.find(a),self.find(b)
        if a!=b: self.p[max(a,b)] = min(a,b)

def reconcile_users(users):
    """High-precision links: at least 2 identical nonempty independent attributes.
    False merges are possible for households; review suspicious clusters manually.
    """
    attrs = ['name','address','phone','email']
    u = users.copy()
    for f in attrs:
        if f not in u: u[f]=''
        u[f] = u[f].map(norm_phone if f=='phone' else clean_text)
    u['id']=pd.to_numeric(u['id'],errors='coerce')
    u=u.dropna(subset=['id']).drop_duplicates('id');u['id']=u['id'].astype(int)
    ds=DSU(u['id'])
    # Candidate pairs must match at least two fields. Inverted index avoids O(n^2).
    matches=defaultdict(int)
    for f in attrs:
        for val, g in u[u[f]!=''].groupby(f):
            ids=g['id'].tolist()
            if len(ids)>250: continue  # Ignore uninformative extremely common values
            for i in range(len(ids)):
                for j in range(i+1,len(ids)):
                    matches[(min(ids[i],ids[j]),max(ids[i],ids[j]))]+=1
    for (a,b),count in matches.items():
        if count>=2: ds.union(a,b)
    groups=defaultdict(list)
    for id in u['id']: groups[ds.find(id)].append(int(id))
    return {int(k):sorted(v) for k,v in groups.items()}, {i:ds.find(i) for i in ds.p}

def read_store(folder):
    u=pd.read_csv(folder/'users.csv').drop_duplicates()
    raw=pd.read_parquet(folder/'orders.parquet').drop_duplicates()
    with (folder/'books.yaml').open(encoding='utf-8') as f: books=yaml.safe_load(f)
    books=pd.DataFrame([{str(k).lstrip(':'):v for k,v in b.items()} for b in books]).drop_duplicates('id')
    return u, raw, books

def parse_dates(series):
    """Return original calendar dates, not UTC-shifted dates.

    Accept year-first ISO date, day-MON-year, and month/day/year strings,
    with arbitrary surrounding clock text and timezone offsets.
    """
    from datetime import date
    from dateutil import parser
    month_names = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    patterns = [
        (re.compile(r"(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)"), 'iso'),
        (re.compile(rf"(?<!\w)(\d{{1,2}})[- /]({month_names})[a-z]*[- /,]+(\d{{4}})(?!\d)",re.I), 'daymonth'),
        (re.compile(rf"(?<!\w)({month_names})[a-z]*[ .-]+(\d{{1,2}})[, .-]+(\d{{4}})(?!\d)",re.I), 'monthday'),
    ]
    def convert(v):
        if v is None or pd.isna(v): return pd.NaT
        text = str(v).strip()
        for pat,fmt in patterns:
            m=pat.search(text)
            if not m: continue
            try:
                if fmt=='iso': y,mo,d=map(int,m.groups())
                elif fmt=='daymonth':
                    d=int(m[1]);mo=parser.parse(m[2]).month;y=int(m[3])
                else:
                    mo=parser.parse(m[1]).month;d=int(m[2]);y=int(m[3])
                return pd.Timestamp(date(y,mo,d))
            except (ValueError,OverflowError): continue
        try:
            t=text.replace('A.M.','AM').replace('P.M.','PM').replace(';',' ')
            return pd.Timestamp(parser.parse(t,fuzzy=True).date())
        except (ValueError,TypeError,OverflowError): return pd.NaT
    return pd.to_datetime(series.map(convert),errors='coerce')

def process_store(folder):
    users, orders, books = read_store(folder)
    orders=orders.copy()
    for col in ('user_id','book_id','quantity'):
        orders[col]=pd.to_numeric(orders[col],errors='coerce')
    orders['timestamp']=parse_dates(orders['timestamp'])
    orders['unit_price_cents']=orders['unit_price'].map(cents)
    # Drop records where reliable monetary calculations are impossible.
    invalid=(orders[['user_id','book_id','quantity','timestamp','unit_price_cents']].isna().any(axis=1) |
             (orders['quantity']<=0) | (orders['quantity']%1!=0))
    bad_count=int(invalid.sum())
    if bad_count:
        sample=orders.loc[invalid,['timestamp','unit_price']].head(8).to_dict('records')
        raise ValueError(f'{folder.name}: {bad_count} invalid orders; inspect sample: {sample}')
    orders=orders.loc[~invalid].copy()
    orders['quantity']=orders['quantity'].astype('int64')
    orders['user_id']=orders['user_id'].astype('int64')
    orders['book_id']=orders['book_id'].astype('int64')
    orders['unit_price_cents']=orders['unit_price_cents'].astype('int64')
    orders['paid_cents']=orders['quantity']*orders['unit_price_cents']
    orders['paid_price']=orders['paid_cents']/100
    orders['date']=orders['timestamp'].dt.strftime('%Y-%m-%d')
    groups, lookup=reconcile_users(users)
    orders['canonical_user_id']=orders['user_id'].map(lookup).fillna(orders['user_id']).astype('int64')
    # Attach author sets to books. Commas delimit authors in the source YAML.
    books['authors']=books.get('author',pd.Series(index=books.index,dtype='object')).map(
        lambda v: tuple(sorted(set(p.strip() for p in str(v).split(',') if p.strip()))) if pd.notna(v) else tuple())
    books['id']=pd.to_numeric(books['id'],errors='coerce')
    good_books=books.dropna(subset=['id']).copy();good_books['id']=good_books['id'].astype('int64')
    orders=orders.merge(good_books[['id','authors']],left_on='book_id',right_on='id',how='left',validate='many_to_one')
    orders['authors']=orders['authors'].map(lambda a:a if isinstance(a,tuple) else tuple())
    revenue=orders.groupby('date')['paid_cents'].sum().sort_index()
    sold=orders[orders['authors'].map(bool)].groupby('authors')['quantity'].sum().sort_values(ascending=False)
    spend=orders.groupby('canonical_user_id')['paid_cents'].sum().sort_values(ascending=False)
    winner=int(spend.index[0]) if len(spend) else None
    authors=sorted(set(books['authors'])-{tuple()})
    metrics={
        'store':folder.name,'total_revenue':round(int(revenue.sum())/100,2),
        'top_five_days':[{'date':str(d),'revenue':int(v)/100} for d,v in revenue.sort_values(ascending=False).head(5).items()],
        'unique_users':len(groups), 'unique_author_sets':len(authors),
        'most_popular_authors':list(sold.index[0]) if len(sold) else [],
        'most_popular_sold_count':int(sold.iloc[0]) if len(sold) else 0,
        'best_buyer_ids':groups.get(winner,[winner]) if winner is not None else [],
        'best_buyer_spend':int(spend.iloc[0])/100 if len(spend) else 0,
        'daily_revenue':[{'date':str(d),'revenue':int(v)/100} for d,v in revenue.items()],
        'quality':{'raw_orders':len(pd.read_parquet(folder/'orders.parquet')),'clean_orders':len(orders),'invalid_orders_dropped':bad_count,'users_rows':len(users),'books_rows':len(books),'unmatched_book_orders':int(orders['authors'].map(lambda x:not bool(x)).sum()),'unknown_user_orders':int((~orders['user_id'].isin(users['id'])).sum())}
    }
    return metrics

def main():
    out={p.name:process_store(p) for p in sorted(BASE.glob('STORE*')) if p.is_dir()}
    dest=Path(__file__).parent/'results.json';dest.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Results saved:',dest)
    for key,d in out.items(): print(key,'customers',d['unique_users'],'revenue',d['total_revenue'])

if __name__=='__main__': main()
