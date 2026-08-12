import gzip
import json
import os
import urllib.request

URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "angel_tokens.json.gz")

# Canonical TradeMetrix symbols -> Angel scrip-master index tokens. The scrip
# master names indices "Nifty 50"/"Nifty Bank" etc. while the app uses
# "NSE:NIFTY50-INDEX" — alias them so feed/quote resolution works.
INDEX_ALIASES = {
    "NSE:NIFTY50-INDEX": "99926000",
    "NSE:NIFTYBANK-INDEX": "99926009",
    "NSE:FINNIFTY-INDEX": "26037",
    "NSE:MIDCPNIFTY-INDEX": "26074",
    "BSE:SENSEX-INDEX": "99919000",
    "NSE:SENSEX-INDEX": "99919000",
    "NSE:INDIAVIX-INDEX": "99926017",
    "NSE:NIFTYIT-INDEX": "99926008",
    "NSE:NIFTYPHARMA-INDEX": "99926023",
    "NSE:NIFTYAUTO-INDEX": "99926029",
    "NSE:NIFTYFMCG-INDEX": "99926021",
    "NSE:NIFTYMETAL-INDEX": "99926030",
    "NSE:NIFTYREALTY-INDEX": "99926018",
    "NSE:NIFTYENERGY-INDEX": "99926020",
    "NSE:NIFTYMEDIA-INDEX": "99926031",
    "NSE:NIFTYPSUBANK-INDEX": "99926025",
    "NSE:NIFTYPVTBANK-INDEX": "99926047",
    "NSE:NIFTYCONSR-INDEX": "99926036",
    "NSE:NIFTYDIVOP-INDEX": "99926034",
    "NSE:NIFTYGSEC-INDEX": "99926055",
    "NSE:NIFTY100-INDEX": "99926012",
    "NSE:NIFTY200-INDEX": "99926033",
    "NSE:NIFTYMIDCAP-INDEX": "99926011",
    "NSE:NIFTYNEXT50-INDEX": "99926013",
}


def main():
    print(f"Downloading scrip master from {URL} ...")
    resp = urllib.request.urlopen(URL, timeout=120)
    data = json.loads(resp.read().decode())

    lookup: dict[str, str] = {}
    for entry in data:
        sym = entry.get("symbol", "")
        seg = entry.get("exch_seg", "")
        tok = entry.get("token", "")
        if sym and seg and tok:
            lookup[f"{seg}:{sym}"] = tok
    lookup.update(INDEX_ALIASES)

    compressed = gzip.compress(json.dumps(lookup, separators=(",", ":")).encode())
    with open(OUT, "wb") as f:
        f.write(compressed)
    print(f"Wrote {len(lookup)} entries to {OUT} ({len(compressed)} bytes compressed)")


if __name__ == "__main__":
    main()
