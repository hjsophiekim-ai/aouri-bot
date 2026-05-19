import json

with open(r'C:\Users\FURSYS\Desktop\aouribot\aouri-bot\runtime\data\question_sessions\67e195646fa2489589b280b0b32d5a82.json', encoding='utf-8') as f:
    d = json.load(f)

rr = d.get('review_result') or {}
crs = rr.get('clause_results', [])
clause_meta = rr.get('clause_meta') or {}
ui_ids = set(str(x) for x in (clause_meta.get('show_ids') or []))

print(f"total crs: {len(crs)}, ui_ids: {len(ui_ids)}")

missing_rewrite = []
for cr in crs:
    if not isinstance(cr, dict):
        continue
    cid = str(cr.get('clause_id') or '')
    if not cid or cid not in ui_ids:
        continue
    if bool(cr.get('keep_as_is')):
        continue
    if bool(cr.get('dedup_suppressed')):
        continue
    if bool(cr.get('guardrail_block')):
        continue
    tier = str(cr.get('risk_tier') or '').upper()
    if tier not in ('HIGH', 'MEDIUM'):
        continue
    must = bool(cr.get('must_fix'))
    appr = bool(cr.get('approval_required'))
    if not must and not appr:
        print(f"  SKIP(soft): {cid} tier={tier}")
        continue
    disp = str(cr.get('display_kind') or '')
    if disp == 'guidance':
        print(f"  SKIP(guidance): {cid} tier={tier} must={must} appr={appr}")
        continue
    is_cl = bool(cr.get('is_checklist_item'))
    if is_cl:
        print(f"  SKIP(checklist): {cid} tier={tier}")
        continue
    sr = cr.get('suggested_rewrite')
    sr_ok = isinstance(sr, str) and bool(sr.strip())
    print(f"  CHECK: {cid} tier={tier} must={must} appr={appr} sr_ok={sr_ok}")
    if not sr_ok:
        missing_rewrite.append(f"{cid}:{tier}")

print()
print('missing_rewrite:', missing_rewrite)
print('RESULT:', 'PASS' if not missing_rewrite else 'FAIL')
