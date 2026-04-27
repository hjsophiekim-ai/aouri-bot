# 180) Lawyer-grade 벤치마크 스위트(초안)

- ai_mode: `off` / law_mode: `off`
- 입력: runtime/tests/fixtures 기반 10종(확장 가능)

## 결과 요약

- app_dev: score=45 tier_counts={'must': 6, 'medium': 2, 'low': 0} ai_used=False docx_strike=True notes=ai_not_used,changed_segments_empty
- purchase_install: score=45 tier_counts={'must': 3, 'medium': 0, 'low': 2} ai_used=False docx_strike=True notes=ai_not_used,changed_segments_empty
- services: score=5 tier_counts={'must': 0, 'medium': 0, 'low': 0} ai_used=False docx_strike=False notes=ai_not_used,no_must_items,no_must_rewrites,docx_redline_markers_missing,changed_segments_empty
- ads_model: score=5 tier_counts={'must': 0, 'medium': 0, 'low': 0} ai_used=False docx_strike=False notes=ai_not_used,no_must_items,no_must_rewrites,docx_redline_markers_missing,changed_segments_empty
- privacy: score=45 tier_counts={'must': 1, 'medium': 1, 'low': 0} ai_used=False docx_strike=True notes=ai_not_used,changed_segments_empty
- supply: score=5 tier_counts={'must': 0, 'medium': 1, 'low': 3} ai_used=False docx_strike=False notes=ai_not_used,no_must_items,no_must_rewrites,docx_redline_markers_missing,changed_segments_empty
- nda: score=5 tier_counts={'must': 0, 'medium': 0, 'low': 0} ai_used=False docx_strike=False notes=ai_not_used,no_must_items,no_must_rewrites,docx_redline_markers_missing,changed_segments_empty
- dealer: score=30 tier_counts={'must': 2, 'medium': 1, 'low': 0} ai_used=False docx_strike=False notes=ai_not_used,docx_redline_markers_missing,changed_segments_empty
- upload_demo: score=45 tier_counts={'must': 3, 'medium': 0, 'low': 0} ai_used=False docx_strike=True notes=ai_not_used,changed_segments_empty
- short: score=5 tier_counts={'must': 0, 'medium': 0, 'low': 0} ai_used=False docx_strike=False notes=ai_not_used,no_must_items,no_must_rewrites,docx_redline_markers_missing,changed_segments_empty

## 산출 JSON(요약)

```json
[
  {
    "case_id": "app_dev",
    "contract_type": "앱개발/소프트웨어개발/SI/유지보수/SaaS",
    "text_len": 513,
    "clause_count": 8,
    "tier_counts": {
      "must": 6,
      "medium": 2,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": true,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.16194331983805668,
      "docx_has_legend": true
    },
    "score": 45,
    "notes": [
      "ai_not_used",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "purchase_install",
    "contract_type": "장비공급/설치/시운전",
    "text_len": 422,
    "clause_count": 5,
    "tier_counts": {
      "must": 3,
      "medium": 0,
      "low": 2
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": true,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.07407407407407407,
      "docx_has_legend": true
    },
    "score": 45,
    "notes": [
      "ai_not_used",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "services",
    "contract_type": "용역/컨설팅",
    "text_len": 222,
    "clause_count": 5,
    "tier_counts": {
      "must": 0,
      "medium": 0,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": false,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.03225806451612903,
      "docx_has_legend": true
    },
    "score": 5,
    "notes": [
      "ai_not_used",
      "no_must_items",
      "no_must_rewrites",
      "docx_redline_markers_missing",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "ads_model",
    "contract_type": "광고/모델",
    "text_len": 222,
    "clause_count": 5,
    "tier_counts": {
      "must": 0,
      "medium": 0,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": false,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.03225806451612903,
      "docx_has_legend": true
    },
    "score": 5,
    "notes": [
      "ai_not_used",
      "no_must_items",
      "no_must_rewrites",
      "docx_redline_markers_missing",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "privacy",
    "contract_type": "개인정보/처리위탁",
    "text_len": 507,
    "clause_count": 5,
    "tier_counts": {
      "must": 1,
      "medium": 1,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": true,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.07865168539325842,
      "docx_has_legend": true
    },
    "score": 45,
    "notes": [
      "ai_not_used",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "supply",
    "contract_type": "물품공급/구매/매매",
    "text_len": 259,
    "clause_count": 5,
    "tier_counts": {
      "must": 0,
      "medium": 1,
      "low": 3
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": false,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.03225806451612903,
      "docx_has_legend": true
    },
    "score": 5,
    "notes": [
      "ai_not_used",
      "no_must_items",
      "no_must_rewrites",
      "docx_redline_markers_missing",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "nda",
    "contract_type": "NDA/비밀유지",
    "text_len": 410,
    "clause_count": 8,
    "tier_counts": {
      "must": 0,
      "medium": 0,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": false,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.03076923076923077,
      "docx_has_legend": true
    },
    "score": 5,
    "notes": [
      "ai_not_used",
      "no_must_items",
      "no_must_rewrites",
      "docx_redline_markers_missing",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "dealer",
    "contract_type": "대리점/유통",
    "text_len": 360,
    "clause_count": 9,
    "tier_counts": {
      "must": 2,
      "medium": 1,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": false,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.04,
      "docx_has_legend": true
    },
    "score": 30,
    "notes": [
      "ai_not_used",
      "docx_redline_markers_missing",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "upload_demo",
    "contract_type": "all",
    "text_len": 182,
    "clause_count": 4,
    "tier_counts": {
      "must": 3,
      "medium": 0,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": true,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.07547169811320754,
      "docx_has_legend": true
    },
    "score": 45,
    "notes": [
      "ai_not_used",
      "changed_segments_empty"
    ]
  },
  {
    "case_id": "short",
    "contract_type": "all",
    "text_len": 37,
    "clause_count": 1,
    "tier_counts": {
      "must": 0,
      "medium": 0,
      "low": 0
    },
    "ai": {
      "enabled": false,
      "used": false,
      "selected_clause_ids": [],
      "selected_count": 0,
      "model": null,
      "ok": null,
      "error": null,
      "usage": null
    },
    "docx": {
      "docx_has_strike": false,
      "docx_has_red": true,
      "docx_red_run_ratio": 0.034482758620689655,
      "docx_has_legend": true
    },
    "score": 5,
    "notes": [
      "ai_not_used",
      "no_must_items",
      "no_must_rewrites",
      "docx_redline_markers_missing",
      "changed_segments_empty"
    ]
  }
]
```
