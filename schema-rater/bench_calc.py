"""Benchmark: full vs targeted calculation for Excess Follow rater."""
import time, json, formulas

wb = r"C:\Users\Siddhesh\Cogitate-project-v2\backend\data\raters\d56bd5ca-4c0a-45a8-aec0-f0ea02d47265\Rater - Excess Follow Form v2024.1.xlsx"
schema_path = r"C:\Users\Siddhesh\Cogitate-project-v2\backend\data\raters\d56bd5ca-4c0a-45a8-aec0-f0ea02d47265\schema.json"

with open(schema_path) as f:
    schema = json.load(f)

print("Loading model...")
t0 = time.time()
xl = formulas.ExcelModel().loads(wb).finish()
t1 = time.time()
print(f"Model load: {t1-t0:.2f}s")
print(f"Nodes in model: {len(xl.dsp.nodes)}")

filename = "Rater - Excess Follow Form v2024.1.xlsx"

# Build output keys
output_keys = []
for field in schema["output_fields"]:
    sheet = field.get("sheet", "")
    cell = field.get("cell_ref", "").replace("$", "")
    if sheet and cell:
        key = f"'[{filename}]{sheet.upper()}'!{cell}"
        output_keys.append(key)

print(f"\nOutput keys count: {len(output_keys)}")
print(f"Sample: {output_keys[:3]}")

# Test full calculation
print("\n--- Full calculate (all nodes) ---")
t2 = time.time()
sol_full = xl.calculate()
t3 = time.time()
print(f"Time: {t3-t2:.2f}s, solution keys: {len(sol_full)}")

# Test targeted calculation
print("\n--- Targeted calculate (only needed outputs) ---")
t4 = time.time()
sol_targeted = xl.calculate(outputs=output_keys)
t5 = time.time()
print(f"Time: {t5-t4:.2f}s, solution keys: {len(sol_targeted)}")

# Verify results match
print("\n--- Verification ---")
mismatches = 0
for key in output_keys:
    norm = key.upper().replace("$", "")
    full_val = None
    targ_val = None
    for k, v in sol_full.items():
        if k.upper().replace("$", "") == norm:
            full_val = v
            break
    for k, v in sol_targeted.items():
        if k.upper().replace("$", "") == norm:
            targ_val = v
            break
    if str(full_val) != str(targ_val):
        mismatches += 1
        print(f"  MISMATCH {key}: full={full_val} vs targeted={targ_val}")

if mismatches == 0:
    print("All outputs match between full and targeted calculation!")
else:
    print(f"{mismatches} mismatches found")
