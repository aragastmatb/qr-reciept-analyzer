import streamlit as st
from datetime import datetime
import pandas as pd
from pathlib import Path
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

from src.db import init_db, insert_tx, list_tx, add_rule, current_balance, get_all_rules, update_rule, delete_rule, update_tx, delete_tx
from src.categorize import guess_category, normalize_store
from src.receipt import parse_from_qr_image, parse_from_url

st.set_page_config(page_title="SRB QR Receipt Tracker", layout="wide")

DB_PATH = Path("data/receipts.db")
init_db(DB_PATH)

st.title("📄 Serbian QR Receipt Tracker")

with open(".streamlit/auth.yaml", "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

try:
    authenticator.login()
except Exception as e:
    st.error(e)
if st.session_state.get('authentication_status'):
    authenticator.logout()
    st.write(f'Welcome *{st.session_state.get("name")}*')
    tab_add, tab_history, tab_rules = st.tabs(["➕ Add", "📜 History", "⚙️ Rules"])
    with tab_add:
        def save_record(ts, store, amount_rsds, category, raw_url=None, meta=None, kind="expense"):
            try:
                iso = datetime.fromisoformat(ts).isoformat()
            except Exception:
                try:
                    iso = pd.to_datetime(ts).to_pydatetime().isoformat()
                except Exception:
                    iso = datetime.now().isoformat()
            insert_tx(DB_PATH, {
                "ts": iso,
                "store": store,
                "amount": float(amount_rsds),
                "category": category,
                "currency": "RSD",
                "source": "qr" if raw_url else "manual",
                "raw_url": raw_url or None,
                "meta_json": meta or {},
                "kind": kind
            })
            st.success("✅ Saved")

        url = ""
        store = ""
        amount = None
        dt_str = ""
        file = st.file_uploader("Upload receipt photo/scan (JPG/PNG)", type=["jpg","jpeg","png"])
        if file:
            with st.spinner("Scanning QR..."):
                parsed_qr = parse_from_qr_image(file)
            if parsed_qr and parsed_qr.get("url"):
                url = parsed_qr["url"]
                st.code(url, language="text")
                with st.spinner("Parsing URL data..."):
                    p = parse_from_url(url)
                    mode = "qr_image"
            else:
                st.error("QR not found in image.")
                p = {}
        else:
            p = {}
            url = ""
        url = st.text_input("QR URL", placeholder="Paste receipt URL")
        if url:
            p = parse_from_url(url)
            mode = "url_input"
        elif p == {}:
            p = {}
            mode = "manual"
        store = normalize_store(p.get("store") or "")
        amount = float(p.get("amount") or 0) if p.get("amount") else None
        dt_str = p.get("ts") or ""
        balance = current_balance(DB_PATH)
        st.metric("Current balance", f"{balance:,.2f} RSD".replace(",", " "))
        col1, col2, col3, col4 = st.columns([2,1,2,1])
        with col1:
            store = st.text_input("Store", value=store)
        with col2:
            amount = st.number_input("Amount (RSD)", min_value=0.0, step=10.0, value=float(amount) if amount else 0.0, format="%.2f")
        with col3:
            dt_str = st.text_input("Date/time", value=dt_str or datetime.now().isoformat(timespec="seconds"))
        with col4:
            category = st.text_input("Category", value=guess_category(store, db=DB_PATH))
        col_type, _ = st.columns([1,3])
        with col_type:
            tx_kind = st.radio("Type", ["expense", "income"], index=0, horizontal=True)

        col_save = st.columns([1])
        with col_save[0]:
            if st.button("💾 Save"):
                if not store or not amount:
                    st.error("Store and Amount required.")
                else:
                    save_record(dt_str, store, amount, category, raw_url=url, meta={"source": mode}, kind=tx_kind)
    with tab_history:
        st.header("📜 History")

        df = pd.DataFrame(list_tx(DB_PATH, limit=2000))
        if not df.empty:
            balance = current_balance(DB_PATH)
            st.metric("Current balance", f"{balance:,.2f} RSD".replace(",", " "))

            df["date"] = pd.to_datetime(df["ts"]).dt.date
            c1, c2, c3 = st.columns(3)
            with c1:
                date_from = st.date_input("From date", value=df["date"].min())
            with c2:
                date_to = st.date_input("To date", value=df["date"].max())
            with c3:
                cat_filter = st.multiselect("Categories", options=sorted(df["category"].unique()),
                                            default=list(sorted(df["category"].unique())))

            df["date"] = pd.to_datetime(df["date"]).dt.date
            mask = (df["date"] >= date_from) & (df["date"] <= date_to) & (df["category"].isin(cat_filter))
            fdf = df.loc[mask].copy()
            fdf = fdf[["id","ts","store","amount","currency","category","kind"]]
            fdf["__delete"] = False
            edited = st.data_editor(
                fdf,
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
                column_config={
                    "id": st.column_config.NumberColumn("id", disabled=True),
                    "ts": st.column_config.TextColumn("Date/time"),
                    "store": st.column_config.TextColumn("Store/Source"),
                    "amount": st.column_config.NumberColumn("Amount (RSD)", step=0.01, format="%.2f"),
                    "currency": st.column_config.TextColumn("Currency"),
                    "category": st.column_config.TextColumn("Category"),
                    "kind": st.column_config.SelectboxColumn("Type", options=["expense","income"]),
                    "__delete": st.column_config.CheckboxColumn("Delete"),
                },
            )

            csave, cdel = st.columns([1,1])
            with csave:
                if st.button("💾 Save changes"):
                    for _, row in edited.iterrows():
                        tx_id = int(row["id"])
                        try:
                            amount = float(row["amount"])
                        except Exception:
                            continue
                        try:
                            ts_iso = pd.to_datetime(row["ts"]).to_pydatetime().isoformat()
                        except Exception:
                            ts_iso = str(row["ts"])

                        update_tx(
                            DB_PATH, tx_id,
                            ts=ts_iso,
                            store=str(row["store"]).strip(),
                            amount=amount,
                            currency=str(row.get("currency") or "RSD").strip(),
                            category=str(row["category"]).strip(),
                            kind=str(row["kind"]).strip(),
                        )
                    st.success("Changes saved")

            with cdel:
                if st.button("🗑 Delete selected"):
                    ids_to_delete = [int(row["id"]) for _, row in edited.iterrows() if bool(row["__delete"])]
                    for tx_id in ids_to_delete:
                        delete_tx(DB_PATH, tx_id)
                    st.success(f"Deleted records: {len(ids_to_delete)}")

            inc = fdf.loc[fdf["kind"]=="income","amount"].sum()
            exp = fdf.loc[fdf["kind"]=="expense","amount"].sum()
            st.write(f"**Total income:** {inc:.2f} RSD  •  **Total expenses:** {exp:.2f} RSD  •  **Balance (filtered):** {(inc-exp):.2f} RSD")

            st.subheader("Total by category")
            cat_sum = fdf.loc[fdf["kind"]=="expense"].groupby("category")["amount"].sum().sort_values(ascending=False)
            st.bar_chart(cat_sum)

            st.subheader("Total by month")
            fdf["month"] = pd.to_datetime(fdf["ts"]).dt.strftime("%Y-%m")
            month_sum = fdf.loc[fdf["kind"]=="expense"].groupby(["month","category"])["amount"].sum()
            st.line_chart(month_sum.unstack(fill_value=0))
        else:
            st.info("No records yet.")
    with tab_rules:
        st.subheader("Auto-categorization Rules")
        rules = get_all_rules(DB_PATH)
        import pandas as pd
        df_rules = pd.DataFrame(rules) if rules else pd.DataFrame(columns=["id","pattern","category","enabled","priority"])

        edited = st.data_editor(
            df_rules,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "id": st.column_config.NumberColumn("id", disabled=True),
                "pattern": st.column_config.TextColumn("Regex (re, IGNORECASE=True)"),
                "category": st.column_config.TextColumn("Category"),
                "enabled": st.column_config.CheckboxColumn("Enabled"),
                "priority": st.column_config.NumberColumn("Priority (lower = first)")
            },
            hide_index=True
        )

        colA, colB, colC = st.columns([1,1,1])
        with colA:
            if st.button("💾 Save changes to DB"):
                for _, row in edited.iterrows():
                    rid = int(row.get("id")) if pd.notna(row.get("id")) else None
                    pat = str(row.get("pattern") or "").strip()
                    cat = str(row.get("category") or "").strip()
                    en  = 1 if bool(row.get("enabled")) else 0
                    pr  = int(row.get("priority") or 100)
                    if not pat or not cat:
                        continue
                    if rid:
                        update_rule(DB_PATH, rid, pat, cat, en, pr)
                    else:
                        add_rule(DB_PATH, pat, cat, en, pr)
                st.success("Done. Rules saved.")

        with colB:
            del_ids = st.text_input("Delete IDs (comma-separated)", placeholder="example: 7, 12")
            if st.button("🗑 Delete"):
                ids = [s.strip() for s in del_ids.split(",") if s.strip()]
                for s in ids:
                    try: delete_rule(DB_PATH, int(s))
                    except: pass
                st.success("Deleted (if IDs existed).")

        with colC:
            st.info("Add new row directly in table (last empty row). Then click «Save changes».")

elif st.session_state.get('authentication_status') is False:
    st.error('Username/password is incorrect')
elif st.session_state.get('authentication_status') is None:
    st.warning('Please enter your username and password')
