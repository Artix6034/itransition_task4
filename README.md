# Bookstore Intelligence — Itransition Task 4

A multi-store BI dashboard for STORE1–STORE5 using the supplied archive.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The dashboard computes on load. Optionally run `python analytics.py` to export `results.json`.

## Contents

- `app.py`: Streamlit dashboard with a tab per store, KPIs, top 5 days, revenue time series, and Q&A for STORE2 and STORE3.
- `analytics.py`: independent ETL, date parsing, USD/EUR prices (including mixed dollar/euro/cent notations), author sets, and user linkage.
- `data/STORE1` ... `data/STORE5`: original supplied input files.

## Definitions and limitations

- For prices, 1 EUR = 1.2 USD, rounding to nearest cent (half up) per unit. `paid_price` is order quantity × rounded unit price.
- Revenue groups by the calendar date **written in the source** timestamp; time-zone offsets do not change the recorded day.
- Unique author sets are sorted, deduplicated comma-separated author names. A single author and a pair are distinct sets.
- Potential aliases are linked by a minimum of two matching nonempty attributes from name, address, phone, email. Matching is transitive via union-find. Shared household details can create false positives; review ambiguous clusters if you need exact identity counts.
- Chat is **metric-grounded rules**, not generative AI; it answers questions about the dashboard metrics without an external API key.
- Unexpected invalid orders raise an explicit error rather than silently omitting revenue. Verify any new input format before changing assumptions.

## Deployment

1. Publish the `bookstore_analytics` project to GitHub. Ensure the `data` folder is included in your repository and permitted to publish.
2. In [Streamlit Community Cloud](https://share.streamlit.io), choose the repo and set entrypoint `app.py`.
3. Test all STORE tabs and the two chat areas at the resulting public URL.
4. Send both repository and public dashboard URLs to `p.lebedev@itransition.com` yourself.

No repository, public dashboard, or email is automatically created by this archive.

## Known verification gap

The generated package was syntax-checked; runtime verification against Parquet requires `pyarrow`, which was unavailable in the authoring environment. Launch locally / on Streamlit Cloud and review results and any validation exceptions before submission.
