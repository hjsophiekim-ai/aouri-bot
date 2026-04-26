from __future__ import annotations

import json
from urllib import request


def main() -> None:
    sid = "38e3d2ecdf7b42b19006d2b1364cb077"
    req = request.Request(
        "http://127.0.0.1:8787/api/revision/download_docx",
        data=json.dumps({"session_id": sid}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    data = request.urlopen(req, timeout=30).read()
    print("bytes=", len(data))
    print("magic=", data[:4].hex())


if __name__ == "__main__":
    main()
