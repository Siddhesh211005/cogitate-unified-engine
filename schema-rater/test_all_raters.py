"""Test all 4 sample raters: upload → calculate defaults → verify outputs."""
import requests
import json
import os

BASE = "http://127.0.0.1:8000/api"
SAMPLE_DIR = r"C:\Users\Siddhesh\Cogitate-project-v2\docs\sample rater inputs"

files = [f for f in os.listdir(SAMPLE_DIR) if f.endswith(".xlsx")]
print(f"Found {len(files)} raters to test\n")

for fname in sorted(files):
    path = os.path.join(SAMPLE_DIR, fname)
    print(f"{'='*60}")
    print(f"RATER: {fname}")
    print(f"{'='*60}")

    # Upload
    with open(path, "rb") as f:
        resp = requests.post(f"{BASE}/upload", files={"file": (fname, f)})

    if resp.status_code != 200:
        print(f"  UPLOAD FAILED: {resp.status_code}")
        try:
            print(f"  {resp.json()}")
        except Exception:
            print(f"  Response: {resp.text[:200]}")
        print()
        continue

    data = resp.json()
    rater_id = data["rater_id"]
    schema = data["schema"]
    print(f"  rater_id:     {rater_id}")
    print(f"  rater_name:   {data['rater_name']}")
    print(f"  sheets:       {len(schema['sheets'])}")
    print(f"  input_fields: {len(schema['input_fields'])}")
    print(f"  output_fields:{len(schema['output_fields'])}")
    print(f"  lookups:      {len(schema['lookup_tables'])}")

    if schema['input_fields']:
        print(f"  Sample inputs:")
        for fld in schema['input_fields'][:3]:
            print(f"    - {fld['name']} ({fld['field_type']}) = {fld['default_value']}")

    if schema['output_fields']:
        print(f"  Output fields:")
        for fld in schema['output_fields']:
            print(f"    - {fld['name']} (cell={fld['cell_ref']})")

    # Calculate defaults
    resp2 = requests.post(f"{BASE}/calculate/defaults", json={"rater_id": rater_id, "inputs": {}})
    if resp2.status_code == 200:
        calc = resp2.json()
        print(f"  DEFAULT OUTPUTS: {json.dumps(calc['outputs'], indent=4)}")
        if calc['warnings']:
            print(f"  WARNINGS: {calc['warnings'][:3]}")
    else:
        try:
            print(f"  CALCULATE FAILED: {resp2.status_code} - {resp2.json()}")
        except Exception:
            print(f"  CALCULATE FAILED: {resp2.status_code} - {resp2.text[:200]}")

    print()
