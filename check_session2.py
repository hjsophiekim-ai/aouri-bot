import json

with open(r'C:\Users\FURSYS\Desktop\aouribot\aouri-bot\runtime\data\question_sessions\67e195646fa2489589b280b0b32d5a82.json', encoding='utf-8') as f:
    d = json.load(f)

rr = d.get('review_result') or {}
crs_all = rr.get('clause_results', [])

# Simulate server: filter out is_checklist_item
crs_for_docx = [cr for cr in crs_all if isinstance(cr, dict) and not cr.get('is_checklist_item')]
checklist_items = [cr for cr in crs_all if isinstance(cr, dict) and cr.get('is_checklist_item')]
print(f"clause_results_for_docx: {len(crs_for_docx)}")
print(f"checklist_items: {len(checklist_items)}")

# original_clauses
orig_clauses = rr.get('original_clauses') or d.get('original_clauses') or []
orig_ids = {str(c.get('clause_id') or '') for c in orig_clauses if isinstance(c, dict)}
print(f"orig_ids count: {len(orig_ids)}")

# Check missing_in_original
cr_ids = {str(c.get('clause_id') or '') for c in crs_for_docx}
missing_in_original = sorted([cid for cid in cr_ids if cid and cid not in orig_ids])
print(f"missing_in_original: {missing_in_original}")

# Build ui_ids
def risk_tier(cr):
    if bool(cr.get('approval_required')) or bool(cr.get('high_risk')):
        return 'HIGH'
    rt = cr.get('risk_tier')
    if isinstance(rt, str) and rt.strip().upper() in ('HIGH','MEDIUM','LOW'):
        return rt.strip().upper()
    return 'MEDIUM' if bool(cr.get('unfavorable_to_us')) else 'LOW'

def ui_visible(cr):
    tier = str(cr.get('risk_tier') or '').strip().upper()
    if tier not in ('HIGH','MEDIUM','LOW'):
        tier = risk_tier(cr)
    return bool(
        cr.get('user_focus_hit') or cr.get('factual_hit') or
        cr.get('approval_required') or cr.get('high_risk') or
        tier in ('HIGH','MEDIUM')
    )

ui_ids = {str(cr.get('clause_id') or '') for cr in crs_for_docx if isinstance(cr, dict) and ui_visible(cr) and str(cr.get('clause_id') or '')}
print(f"ui_ids count: {len(ui_ids)}, items: {sorted(ui_ids)}")

# Simulate consistency check WITH new fix
print()
missing_rewrite = []
for cr in crs_for_docx:
    if not isinstance(cr, dict):
        continue
    cid = str(cr.get('clause_id') or '')
    if not cid or cid not in ui_ids:
        continue
    if bool(cr.get('keep_as_is')): continue
    if bool(cr.get('dedup_suppressed')): continue
    if bool(cr.get('guardrail_block')): continue
    tier = risk_tier(cr)
    if tier not in ('HIGH','MEDIUM'): continue
    must = bool(cr.get('must_fix'))
    appr = bool(cr.get('approval_required'))
    if not must and not appr:
        print(f"  SKIP(soft): {cid}")
        continue
    disp = str(cr.get('display_kind') or '')
    if disp == 'guidance':
        print(f"  SKIP(guidance): {cid} tier={tier} must={must} appr={appr}")
        continue
    is_cl = bool(cr.get('is_checklist_item'))
    if is_cl:
        print(f"  SKIP(checklist): {cid}")
        continue
    sr = cr.get('suggested_rewrite')
    sr_ok = isinstance(sr, str) and bool(sr.strip())
    print(f"  CHECK: {cid} tier={tier} must={must} appr={appr} sr_ok={sr_ok}")
    if not sr_ok:
        missing_rewrite.append(f"{cid}:{tier}")

print()
print('missing_rewrite:', missing_rewrite)
print('RESULT:', 'PASS' if not missing_rewrite else 'FAIL')
