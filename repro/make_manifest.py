#!/usr/bin/env python3
"""Build `repro/data_manifest.json`: path, size and sha256 of every file the
reproduction needs (package code, criteria, scripts and the Terminal-Bench 2.1
trajectories).

Why a manifest: the upstream repository is 440 MB, and in this environment
github.com / raw.githubusercontent.com are not reachable while the jsDelivr CDN
is, so `repro/fetch_data.py` pulls individual files from the CDN and verifies
them against this manifest. Regenerate it only if you intentionally move to a
different upstream commit.

Usage:
    python repro/make_manifest.py            # from a local checkout
"""

import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PREFIXES = ("llm_verifier/", "scripts/", "criteria/",
            "data/terminal_bench_2.1_trajs/")
FILES = ("README.md", "pyproject.toml", "requirements.txt", ".env.example",
         "CHANGELOG.md", "add_new_benchmark.md", "LICENSE", ".gitignore")


def wanted(rel):
    return rel in FILES or rel.startswith(PREFIXES)


def main():
    entries = []
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir.startswith((".git", ".venv", "cache", "results", "logs",
                               "repro", "data_generators")):
            continue
        for name in filenames:
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            rel = rel.replace(os.sep, "/")
            if not wanted(rel):
                continue
            path = os.path.join(ROOT, rel)
            blob = open(path, "rb").read()
            entries.append({"path": rel, "size": len(blob),
                            "sha256": hashlib.sha256(blob).hexdigest()})
    entries.sort(key=lambda e: e["path"])
    out = os.path.join(ROOT, "repro", "data_manifest.json")
    json.dump({"upstream": "llm-as-a-verifier/llm-as-a-verifier@main",
               "n_files": len(entries),
               "total_bytes": sum(e["size"] for e in entries),
               "files": entries}, open(out, "w"), indent=1)
    print(f"wrote {out}: {len(entries)} files, "
          f"{sum(e['size'] for e in entries) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
