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
