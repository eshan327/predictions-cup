"""Validate archived successful REST bodies against the retrieved official schema."""

import argparse
import json
import re
import sqlite3
from pathlib import Path

from jsonschema import Draft202012Validator

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--schemas", default="docs/api/read-schemas.json")
args = parser.parse_args()
spec = json.loads(Path(args.schemas).read_text())
counts, errors = {}, []
with sqlite3.connect(args.db) as db:
    for oid, path, body in db.execute("SELECT id,path,body FROM observations"):
        route = re.sub(r"/exchanges/\d+/", "/exchanges/{id}/", path)
        route = re.sub(r"/tournaments/[^/]+", "/tournaments/{slug}", route)
        if route not in spec["responses"] or route == "/account":
            continue  # Account archive intentionally omits personal profile fields.
        schema = {**spec["responses"][route], "components": spec["components"]}
        counts[route] = counts.get(route, 0) + 1
        for error in Draft202012Validator(schema).iter_errors(json.loads(body)):
            errors.append(
                {
                    "observation": oid,
                    "route": route,
                    "field": list(error.path),
                    "validator": error.validator,
                }
            )
print(json.dumps({"validated": counts, "errors": errors}, indent=2))
raise SystemExit(1 if errors else 0)
