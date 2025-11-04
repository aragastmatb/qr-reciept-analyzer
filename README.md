# Serbian QR Receipt Tracker (Streamlit)

Python/Streamlit application: reading **QR** codes from Serbian receipts, parsing amount/date/store, auto-categorization and saving to SQLite.

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Features
- Receipt image upload → QR code recognition (pyzbar / OpenCV fallback)
- Manual QR URL input
- Parses amount/date/store from URL parameters or HTML page
- Automatic store categorization based on rules
- SQLite database: transactions + rules
- History, filters by date/categories, summary by categories/months
- Authorization

## License
Apache 2.0 + Commons Clause