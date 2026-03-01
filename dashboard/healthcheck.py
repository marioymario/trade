import urllib.request

URL = "http://127.0.0.1:8501/_stcore/health"

try:
    with urllib.request.urlopen(URL, timeout=1.5) as r:
        body = r.read().decode("utf-8", "ignore").lower()
    raise SystemExit(0 if "ok" in body else 1)
except Exception:
    raise SystemExit(1)
