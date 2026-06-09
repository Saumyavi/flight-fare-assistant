"""Tiny built-in city/airport -> IATA mapping for the MVP.

For anything not in this map we fall back to asking the LLM (see llm_parser.py),
which is good enough for the free-tier MVP. Replace with a real IATA DB later.
"""

CITY_TO_IATA = {
    # India
    "delhi": "DEL", "new delhi": "DEL", "del": "DEL",
    "mumbai": "BOM", "bombay": "BOM", "bom": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR", "blr": "BLR",
    "hyderabad": "HYD", "hyd": "HYD",
    "chennai": "MAA", "madras": "MAA", "maa": "MAA",
    "kolkata": "CCU", "calcutta": "CCU", "ccu": "CCU",
    "goa": "GOI", "dabolim": "GOI", "goi": "GOI", "mopa": "GOX",
    "pune": "PNQ", "pnq": "PNQ",
    "ahmedabad": "AMD", "amd": "AMD",
    "jaipur": "JAI", "jai": "JAI",
    "kochi": "COK", "cochin": "COK", "cok": "COK",
    "trivandrum": "TRV", "thiruvananthapuram": "TRV", "trv": "TRV",
    "lucknow": "LKO", "lko": "LKO",
    "chandigarh": "IXC", "ixc": "IXC",
    "srinagar": "SXR", "sxr": "SXR",
    "leh": "IXL", "ixl": "IXL",
    "guwahati": "GAU", "gau": "GAU",
    "bhubaneswar": "BBI", "bbi": "BBI",
    # Common int'l
    "dubai": "DXB", "dxb": "DXB",
    "singapore": "SIN", "sin": "SIN",
    "bangkok": "BKK", "bkk": "BKK",
    "london": "LON", "heathrow": "LHR", "lhr": "LHR",
    "new york": "NYC", "jfk": "JFK", "nyc": "NYC",
    "paris": "PAR", "cdg": "CDG",
    "tokyo": "TYO", "hnd": "HND", "nrt": "NRT",
}


def resolve_iata(text: str) -> str | None:
    if not text:
        return None
    t = text.strip().lower()
    if len(t) == 3 and t.isalpha():
        return t.upper()
    return CITY_TO_IATA.get(t)
