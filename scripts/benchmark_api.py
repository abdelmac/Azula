"""Mesurer le temps HTTP observé, sans prétendre isoler serveur/réseau/rendu."""
import argparse
import getpass
import http.cookiejar
import json
import math
import os
import platform
import statistics
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:8080")
parser.add_argument("--username", required=True)
parser.add_argument("--requests", type=int, default=500)
parser.add_argument("--concurrency", type=int, default=10)
parser.add_argument("--path", choices=["customers", "invoices", "products", "entries"], default="invoices")
args = parser.parse_args()
if not 1 <= args.requests <= 10000 or not 1 <= args.concurrency <= 50:
    parser.error("Volumes hors limites.")
parsed = urllib.parse.urlsplit(args.url)
if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
    parser.error("URL HTTP(S) sans identifiants attendue.")
if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
    parser.error("HTTPS requis pour un serveur distant.")
password = getpass.getpass("Mot de passe (jamais enregistré) : ")
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
base = args.url.rstrip("/")
with opener.open(base + "/api/auth/csrf/", timeout=15) as response:
    csrf = json.load(response)["csrfToken"]
request = urllib.request.Request(base + "/api/auth/login/", data=json.dumps({"username": args.username, "password": password}).encode(), headers={"Content-Type": "application/json", "X-CSRFToken": csrf, "Referer": base + "/"})
with opener.open(request, timeout=15) as response:
    json.load(response)
password = None
cookie_header = "; ".join(f"{cookie.name}={cookie.value}" for cookie in jar)
url = f"{base}/api/{args.path}/?page_size=50&ordering=-id"


def measure(_):
    started = time.perf_counter()
    req = urllib.request.Request(url, headers={"Cookie": cookie_header})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        payload = json.loads(data)
    return (time.perf_counter() - started) * 1000, len(data), payload["count"]


for _ in range(10):
    measure(0)
started = time.perf_counter()
with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
    results = list(pool.map(measure, range(args.requests)))
durations = sorted(row[0] for row in results)
print(json.dumps({
    "measurement": "HTTP client, includes server + network + response read; excludes browser render",
    "platform": platform.platform(), "python": platform.python_version(), "logical_cpus": os.cpu_count(),
    "endpoint": args.path, "requests": len(results), "concurrency": args.concurrency,
    "warmup_requests": 10, "rows": results[0][2], "page_size": 50,
    "p50_ms": round(statistics.median(durations), 2),
    "p95_ms": round(durations[math.ceil(len(durations) * .95) - 1], 2),
    "elapsed_seconds": round(time.perf_counter() - started, 2),
    "response_bytes_mean": round(statistics.mean(row[1] for row in results)),
}, indent=2))
csrf_cookie = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
with opener.open(urllib.request.Request(base + "/api/auth/logout/", data=b"{}", headers={"Content-Type": "application/json", "X-CSRFToken": csrf_cookie, "Referer": base + "/"}), timeout=15):
    pass
