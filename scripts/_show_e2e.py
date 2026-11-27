import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
print({k: r.get(k + "_status") for k in ("redline", "clean", "report")})
vg = r.get("verification_gate") or {}
print("VG", vg.get("status"), json.dumps(vg.get("unresolved"), ensure_ascii=False)[:600])
print("ROLE", (r.get("deal_flow") or {}).get("role", {}).get("status"), (r.get("deal_flow") or {}).get("role", {}).get("our_label"))
ri = r.get("redline_integrity") or {}
print("RLI", ri.get("counts"), ri.get("error"))
es = r.get("executive_summary") or {}
print("ES", es.get("headline"), es.get("severity_distribution"))
for e in r["edits"]:
    if e["tier"] in ("HIGH", "MEDIUM") or e["edit"]:
        print("-", e["path"], e["tier"], "edit" if e["edit"] else "", "keep" if e["keep"] else "", "|", (e["rewrite"] or e["addition"])[:200].replace("\n", " "))
for h, rows in r.get("business_brief_sections") or []:
    print("##", h)
    for st, tx in rows[:30]:
        print("  ", st, tx[:260])
