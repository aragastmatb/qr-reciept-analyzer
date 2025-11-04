# src/receipt.py
from urllib.parse import urlparse, parse_qs
import re
import requests
from PIL import Image
from datetime import datetime
from bs4 import BeautifulSoup

def _from_string_to_iso(dt_str: str) -> str:
    dateformat = "%d.%m.%Y. %H:%M:%S"
    try:
        dt = datetime.strptime(dt_str, dateformat)
        return dt.isoformat()
    except Exception:
        return ''

def _decode_qr_pyzbar(image) -> str | None:
    try:
        from pyzbar.pyzbar import decode
        codes = decode(image)
        for c in codes:
            if c.type == "QRCODE":
                return c.data.decode("utf-8", errors="ignore")
    except Exception:
        return None
    return None

def _decode_qr_opencv(image) -> str | None:
    try:
        import cv2
        import numpy as np
        cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        det = cv2.QRCodeDetector()
        data, pts, _ = det.detectAndDecode(cv_img)
        return data or None
    except Exception:
        return None

def parse_from_qr_image(file) -> dict[str, any]:
    img = Image.open(file).convert("RGB")
    data = _decode_qr_pyzbar(img) or _decode_qr_opencv(img)
    return {"url": data} if data else {}

def _try_params(url: str) -> dict[str, any]:
    """
    В SUF часть полей иногда лежит в query. Забираем, если есть.
    """
    out: dict[str, any] = {}
    try:
        u = urlparse(url)
        q = parse_qs(u.query)
        def pick(*keys):
            for k in keys:
                v = q.get(k)
                if v and v[0]:
                    return v[0]
            return None
        amt = pick("amt","total","amount","zaUplatu")
        ts  = pick("crtd","dt","time","date")
        store = pick("tinName","seller","store","merchant","company")
        if store: out["store"] = store
        if amt:
            amt = amt.replace(".", "").replace(",", ".")  # 1.234,56 -> 1234.56
            out["amount"] = float(amt)
        if ts: out["ts"] = _from_string_to_iso(ts)
    except Exception:
        pass
    return out

_SERB_STORE_PATTERNS = [
    r"Предузеће[:\s]*</?[^>]*>\s*([^<\n]+)",
    r"Име\s+продајног\s+места[:\s]*</?[^>]*>\s*([^<\n]+)",
    r"Место\s+продаје[:\s]*</?[^>]*>\s*([^<\n]+)",
    r"^\s*([A-Z0-9][A-Z0-9 _\.-]{2,})\s*$"
]
_SERB_TOTAL_PATTERNS = [
    r"Укупан износ[:\s]*</?[^>]*>\s*([\d\.,]+)",
    r"За уплату[:\s]*([\d\.,]+)"
]
_SERB_DATE_PATTERNS = [
    r"ПФР време[^<]*</?[^>]*>\s*([0-9\. :]+)",
    r"Време[^<]*</?[^>]*>\s*([0-9\. :]+)",
    r"(\d{2}\.\d{2}\.\d{4}\.\s+\d{2}:\d{2}:\d{2})"
]

_NUM = re.compile(r'[\s\u00A0]')

def _num_to_cents(s: str) -> int:
    s = _NUM.sub('', s).replace('.', '').replace(',', '.')
    return float(s)

def _find_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(strip=True)
            if txt:
                return txt
    return None

def _find_by_label_text(soup: BeautifulSoup, labels: list[str]) -> str | None:
    rx = re.compile('|'.join(labels), re.I)
    for tag in soup.find_all(text=rx):
        parent = tag.parent
        t = parent.get_text(" ", strip=True)
        m = re.search(r'([0-9\.\,\s\u00A0]+)(RSD|дин|RSD)?', t)
        if m:
            val = m.group(1).strip()
            if re.search(r'\d', val):
                return val
        sib = parent.find_next(string=re.compile(r'\d'))
        if sib:
            val = sib.strip()
            if re.search(r'\d', val):
                return val
    return None

def _extract_html(html: str) -> dict:
    out: dict = {}
    soup = BeautifulSoup(html, "html.parser")

    # ----- STORE -----
    store = _find_text(soup, [
        "#shopFullNameLabel",
        "#sellerNameLabel",
        "span.badge",
        "[data-testid='shopFullName']",
    ])
    if not store:
        pre = soup.find("pre")
        if pre:
            m = re.search(r'^[A-Z0-9][A-Z0-9 _\.\-]{2,}$', pre.get_text(), flags=re.M)
            if m:
                store = m.group(0).strip()
    if store:
        out["store"] = store

    # ----- AMOUNT -----
    amount_txt = _find_text(soup, [
        "#totalAmountLabel",
        "#amountToPayLabel",
        "#amountToPayWithVATLabel",
        "#totalLabel",
    ])
    if not amount_txt:
        amount_txt = _find_by_label_text(soup, [
            r"Укупан\s+износ", r"За\s+уплату", r"Ukupan\s+iznos", r"Total\s+amount",
            r"Iznos\s+za\s+uplatu"
        ])
    if not amount_txt:
        pre = soup.find("pre")
        if pre:
            m = re.search(r"(Укупан износ|За уплату).*?([0-9\.\,\s\u00A0]+)", pre.get_text(), flags=re.I|re.S)
            if m:
                amount_txt = m.group(2).strip()
    if amount_txt:
        try:
            out["amount"] = _num_to_cents(amount_txt)
        except Exception:
            pass

    # ----- DATE/TIME -----
    dt = _find_text(soup, [
        "#sdcDateTimeLabel",
        "#issueDateTimeLabel",
        "[data-testid='issueDateTime']",
    ])
    if not dt:
        # label-based
        cand = _find_by_label_text(soup, [r"ПФР време", r"Време", r"Datum", r"Date"])
        if cand and re.search(r'\d{2}\.\d{2}\.\d{4}\.\s+\d{2}:\d{2}:\d{2}', cand):
            dt = cand
    if not dt:
        pre = soup.find("pre")
        if pre:
            m = re.search(r'(\d{2}\.\d{2}\.\d{4}\.\s+\d{2}:\d{2}:\d{2})', pre.get_text())
            if m:
                dt = m.group(1)
    if dt:
        out["ts"] = _from_string_to_iso(dt)

    return out

def parse_from_url(url: str) -> dict:
    if not url:
        return {}
    result = _try_params(url)

    if not (result.get("store") and result.get("amount") and result.get("ts")):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/127.0 Safari/537.36",
                "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8"
            }
            r = requests.get(url, timeout=15, headers=headers)
            r.encoding = "utf-8"
            if r.ok and r.text:
                html_data = _extract_html(r.text)
                result = {**html_data, **result}
        except Exception:
            pass

    return result

