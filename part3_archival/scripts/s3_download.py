"""Resumable anonymous download of selected S3 keys with checksum verification.
Input: CSV with columns key,size,etag (subset of s3_inventory.csv). Files land in
data/raw/<key minus 'swe-bench-pro/'>. Existing files with matching size+md5 are skipped.
Single-part ETags are MD5 and are verified; multipart ETags ('-') are size-checked only.
Writes <manifest>.done.csv with sha256 for every file.
Usage: python -I s3_download.py <keys_csv> [n_workers]
"""
import csv
import hashlib
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BUCKET = "https://scaleapi-results.s3.amazonaws.com/"
OUT = Path("data/raw")


def digests(p):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def fetch(row):
    key, size, etag = row["key"], int(row["size"]), row["etag"]
    dest = OUT / key.removeprefix("swe-bench-pro/")
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(6):
        if dest.exists() and dest.stat().st_size == size:
            md5, sha = digests(dest)
            if "-" in etag or md5 == etag:
                return key, size, etag, sha, "ok"
        try:
            tmp = dest.with_suffix(dest.suffix + ".part")
            with urllib.request.urlopen(BUCKET + urllib.request.quote(key), timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            os.replace(tmp, dest)
        except Exception as e:
            print("retry", key, attempt, e, file=sys.stderr, flush=True)
            time.sleep(2 ** attempt)
    return key, size, etag, "", "FAILED"


if __name__ == "__main__":
    rows = list(csv.DictReader(open(sys.argv[1])))
    nw = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    done = 0
    with ThreadPoolExecutor(nw) as ex, open(sys.argv[1] + ".done.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "size", "etag", "sha256", "status"])
        for res in ex.map(fetch, rows):
            w.writerow(res)
            done += 1
            if done % 200 == 0:
                print("done", done, "/", len(rows), flush=True)
    print("finished", done)
