"""Anonymous (unsigned HTTPS) inventory of s3://scaleapi-results/swe-bench-pro/.
No credentials, no requester-pays. Writes data/manifests/s3_inventory.csv (key, size, etag, last_modified).
Usage: python -I s3_inventory.py <out_csv>
"""
import csv
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BUCKET = "https://scaleapi-results.s3.amazonaws.com/"
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_all(prefix):
    token = None
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            q["continuation-token"] = token
        for attempt in range(5):
            try:
                with urllib.request.urlopen(BUCKET + "?" + urllib.parse.urlencode(q), timeout=60) as r:
                    root = ET.fromstring(r.read())
                break
            except Exception as e:  # transient network errors
                print("retry", attempt, e, file=sys.stderr)
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError("listing failed")
        for c in root.findall("s:Contents", NS):
            yield (c.find("s:Key", NS).text, int(c.find("s:Size", NS).text),
                   c.find("s:ETag", NS).text.strip('"'), c.find("s:LastModified", NS).text)
        if root.find("s:IsTruncated", NS).text != "true":
            return
        token = root.find("s:NextContinuationToken", NS).text


if __name__ == "__main__":
    n = 0
    with open(sys.argv[1], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "size", "etag", "last_modified"])
        for row in list_all("swe-bench-pro/"):
            w.writerow(row)
            n += 1
    print("objects", n)
