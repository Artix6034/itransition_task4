"""Bookstore BI dashboard — streamlit run app.py"""
from pathlib import Path
import json
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from analytics import process_store, BASE

st.set_page_config(page_title='Bookstore Intelligence',page_icon='📚',layout='wide')
st.markdown('''<style> .block-container{padding-top:2rem;max-width:1320px}div[data-testid="stMetric"]{background:#f5f7fb;padding:20px;border-radius:14px;border:1px solid #e5eaf2}h1{letter-spacing:-1px}</style>''',unsafe_allow_html=True)
st.title('📚 Bookstore Intelligence')
st.caption('Sales performance · Customer reconciliation · Author analytics | USD')
folders=sorted(p for p in BASE.glob('STORE*') if p.is_dir())
if not folders: st.error('Missing data/STORE* folders');st.stop()
@st.cache_data(show_spinner='Analyzing orders and customer records...')
def load_data(name): return process_store(BASE/name)

# Controlled local analytics Q&A: answers grounded in computed metrics, no hallucinated LLM.
def answer(q,d):
    s=q.casefold()
    if any(w in s for w in ('top days','top 5','best day','days','дней','дни')): return '\n'.join(f"{v['date']}: ${v['revenue']:,.2f}" for v in d['top_five_days'])
    if any(w in s for w in ('revenue','sales','выручк','доход')): return f"Total revenue: ${d['total_revenue']:,.2f}."
    if any(w in s for w in ('customer','user','пользоват','клиент')) and not any(w in s for w in ('buyer','spend','best','топ','лучший')): return f"Unique reconciled users: {d['unique_users']:,}."
    if any(w in s for w in ('buyer','spend','best','покупател','трат')): return f"Highest-spending buyer IDs: {d['best_buyer_ids']} · Total: ${d['best_buyer_spend']:,.2f}."
    if any(w in s for w in ('popular','most sold','популяр')): return f"Top-selling author set: {', '.join(d['most_popular_authors'])} · {d['most_popular_sold_count']:,} books sold."
    if any(w in s for w in ('author','автор')): return f"Distinct author sets: {d['unique_author_sets']:,}."
    return 'Try: top 5 days, total revenue, unique users, author sets, most popular authors, or best buyer.'

tabs=st.tabs([p.name for p in folders])
for tab,folder in zip(tabs,folders):
    with tab:
        d=load_data(folder.name)
        st.subheader(folder.name+' · Performance overview')
        c1,c2,c3,c4=st.columns(4)
        c1.metric('Revenue',f"${d['total_revenue']:,.2f}")
        c2.metric('Unique customers',f"{d['unique_users']:,}")
        c3.metric('Unique author sets',f"{d['unique_author_sets']:,}")
        c4.metric('Books sold · top author set',f"{d['most_popular_sold_count']:,}")
        chartcol,tablecol=st.columns([1.8,1],gap='large')
        with chartcol:
            st.markdown('#### Daily revenue')
            daily=pd.DataFrame(d['daily_revenue'])
            fig,ax=plt.subplots(figsize=(10,4))
            if len(daily):
                ax.plot(pd.to_datetime(daily['date']),daily['revenue'],linewidth=1.7,color='#2563eb')
            ax.set_ylabel('Revenue (USD)');ax.set_xlabel('Date');ax.grid(alpha=.18)
            fig.autofmt_xdate();fig.tight_layout();st.pyplot(fig);plt.close(fig)
        with tablecol:
            st.markdown('#### Top 5 revenue days')
            st.dataframe(pd.DataFrame(d['top_five_days']).rename(columns={'date':'Date (YYYY-MM-DD)','revenue':'Revenue (USD)'}),hide_index=True,use_container_width=True)
            st.markdown('#### Leading author set')
            st.write(', '.join(d['most_popular_authors']) or 'Unavailable')
            st.markdown('#### Highest-spending customer')
            st.code(json.dumps(d['best_buyer_ids']))
            st.caption(f"Reconciled spend: ${d['best_buyer_spend']:,.2f}")
        with st.expander('Data quality and assumptions'):
            st.json(d['quality'])
            st.caption('Users are linked when 2 or more nonempty identity attributes match exactly after normalization. Potential shared identifiers may require manual review. Prices are converted to USD with EUR × 1.2, then rounded to cents per unit. Invalid orders are excluded.')
        if folder.name in ('STORE2','STORE3'):
            st.markdown('#### 💬 Ask about this store')
            st.caption('Built-in analytics chat: answerable queries are grounded in this store’s calculated metrics.')
            q=st.chat_input('Ask about sales, customers, authors...',key=f'chat_{folder.name}')
            if q:
                st.chat_message('user').write(q)
                st.chat_message('assistant').write(answer(q,d))
