"""Quick test script for upload + calculate endpoints."""
import requests
import json

BASE = "http://127.0.0.1:8000/api"
RATER_FILE = r"C:\Users\Siddhesh\Cogitate-project-v2\docs\sample rater inputs\Homeowners Rater.xlsx"

# --- Upload ---
print("=== UPLOAD ===")
with open(RATER_FILE, "rb") as f:
    resp = requests.post(f"{BASE}/upload", files={"file": ("Homeowners Rater.xlsx", f)})

print(f"Status: {resp.status_code}")
data = resp.json()

if resp.status_code != 200:
    print(json.dumps(data, indent=2))
    exit(1)

rater_id = data["rater_id"]
rater_name = data["rater_name"]
schema = data["schema"]

print(f"rater_id:  {rater_id}")
print(f"rater_name: {rater_name}")
print(f"Input fields:  {len(schema['input_fields'])}")
print(f"Output fields: {len(schema['output_fields'])}")

print("\n--- Input Fields ---")
for fld in schema["input_fields"]:
    line = f"  {fld['name']:35s} type={fld['field_type']:8s}  sheet={fld['sheet']:20s}  cell={fld['cell_ref']:6s}  default={fld['default_value']}"
    print(line)

print("\n--- Output Fields ---")
for fld in schema["output_fields"]:
    line = f"  {fld['name']:35s} sheet={fld['sheet']:20s}  cell={fld['cell_ref']:6s}  formula={fld.get('formula','')}"
    print(line)

# --- Calculate with defaults ---
print("\n=== CALCULATE (defaults) ===")
resp2 = requests.post(f"{BASE}/calculate/defaults", json={"rater_id": rater_id, "inputs": {}})
print(f"Status: {resp2.status_code}")
calc = resp2.json()
print(f"Outputs: {json.dumps(calc.get('outputs', {}), indent=2)}")
print(f"Warnings: {calc.get('warnings', [])}")

# --- Calculate with overrides ---
print("\n=== CALCULATE (Building_limit=500000) ===")
# Find the field name for building limit
bl_field = None
for fld in schema["input_fields"]:
    if "building" in fld["name"].lower() or "building" in fld.get("label", "").lower():
        bl_field = fld["name"]
        break

if bl_field:
    resp3 = requests.post(f"{BASE}/calculate", json={"rater_id": rater_id, "inputs": {bl_field: 500000}})
    print(f"Status: {resp3.status_code}")
    calc3 = resp3.json()
    print(f"Outputs: {json.dumps(calc3.get('outputs', {}), indent=2)}")
    print(f"Warnings: {calc3.get('warnings', [])}")
else:
    print("Could not find building limit field")
