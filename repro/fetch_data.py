#!/usr/bin/env python3
"""Fetch the upstream files this reproduction needs, from the jsDelivr CDN.

`repro/data_manifest.json` pins every needed file (path, size, sha256) of
`llm-as-a-verifier/llm-as-a-verifier@main`. This script downloads the ones
that are missing or fail verification.

Why not `git clone`? In the environment used for this assignment,
github.com, raw.githubusercontent.com and huggingface.co are not reachable
from the shell (DNS/TLS blackhole), while the jsDelivr CDN is. The upstream
repository is also 440 MB, of which this reproduction needs 58 MB (the
package, criteria, scripts and the Terminal-Bench 2.1 trajectories).
Individual files are still served by the CDN even though its *listing* API
refuses packages over 50 MB — hence the pinned manifest.

Usage:
    python repro/fetch_data.py --check        # verify only, download nothing
    python repro/fetch_data.py                # download what is missing
    python repro/fetch_data.py --jobs 32
"""

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "repro", "data_manifest.json")
REPO = "llm-as-a-verifier/llm-as-a-verifier"
BRANCH = "main"
# Several jsDelivr backends: individual files 403 intermittently on one edge
# and are served fine by another.
BASES = [f"https://cdn.jsdelivr.net/gh/{REPO}@{BRANCH}/",
         f"https://fastly.jsdelivr.net/gh/{REPO}@{BRANCH}/",
         f"https://gcore.jsdelivr.net/gh/{REPO}@{BRANCH}/"]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(entry):
    """(status, reason) for one manifest entry: ok / missing / corrupt."""
    path = os.path.join(ROOT, entry["path"])
    if not os.path.exists(path):
        return "missing", "not downloaded"
    size = os.path.getsize(path)
    if size != entry["size"]:
        return "corrupt", f"size {size} != {entry['size']}"
    if sha256(path) != entry["sha256"]:
        return "corrupt", "sha256 mismatch"
    return "ok", ""


def fetch(entry, attempts=3):
    """Download one file into place, verified against the manifest."""
    out = os.path.join(ROOT, entry["path"])
    os.makedirs(os.path.dirname(out) or ROOT, exist_ok=True)
    quoted = urllib.parse.quote(entry["path"])
    last = "no backend tried"
    for attempt in range(attempts):
        for base in BASES:
            try:
                req = urllib.request.Request(
                    base + quoted, headers={"User-Agent": "Mozilla/5.0"})
                blob = urllib.request.urlopen(req, timeout=90,
                                              context=_CTX).read()
                if len(blob) != entry["size"]:
                    raise IOError(f"size {len(blob)} != {entry['size']}")
                if hashlib.sha256(blob).hexdigest() != entry["sha256"]:
                    raise IOError("sha256 mismatch")
                tmp = out + ".part"
                with open(tmp, "wb") as f:
                    f.write(blob)
                os.replace(tmp, out)
                return None
            except Exception as exc:                      # noqa: BLE001
                last = f"{base.split('/')[2]}: {exc}"
        time.sleep(1.5 * (attempt + 1))
    return last


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify the tree against the manifest, download nothing")
    ap.add_argument("--jobs", type=int, default=24)
    args = ap.parse_args()

    manifest = json.load(open(MANIFEST))
    entries = manifest["files"]
    print(f"manifest: {len(entries)} files, "
          f"{manifest['total_bytes'] / 1e6:.1f} MB ({manifest['upstream']})")

    status = [(e, *check(e)) for e in entries]
    bad = [e for e, s, _ in status if s != "ok"]
    good = len(entries) - len(bad)
    print(f"verified ok: {good} | missing: "
          f"{sum(1 for e, s, _ in status if s == 'missing')} | corrupt: "
          f"{sum(1 for e, s, _ in status if s == 'corrupt')}")
    if args.check or not bad:
        return 0 if not bad else 1

    done = [0]
    failures = []

    def work(entry):
        err = fetch(entry)
        done[0] += 1
        if err:
            failures.append((entry["path"], err))
        if done[0] % 50 == 0 or done[0] == len(bad):
            print(f"  {done[0]}/{len(bad)}", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(work, bad))
    print(f"downloaded {len(bad) - len(failures)}/{len(bad)} in "
          f"{time.time() - t0:.0f}s")
    for path, err in failures[:10]:
        print(f"  FAILED {path}: {err}")
    if not failures:
        print("re-verify: python repro/fetch_data.py --check")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
