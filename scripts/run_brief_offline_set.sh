#!/usr/bin/env bash
# 사업팀 전달본 무과금 재현 세트 — 천안 임대차·PPL·용역 + 임대차 변형 4종을 새 서버 프로세스(캐시 없음)로 업로드→검토→다운로드.
set -u
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
OUT=${1:-reports_evidence/business_brief/after}
mkdir -p "$OUT"
run() {  # name input focus_file_or_log kind [variant]
  local n=$1 f=$2 rf=$3 kind=$4 var=${5:-}
  rm -rf "$OUT/offline_$n"
  python scripts/offline_e2e.py --input "$f" --out-dir "$OUT/offline_$n" --review-focus "$rf" \
    --answers "reports_evidence/${6:-cheonan_lease}/config/answers.json" > "$OUT/offline_$n.log" 2>&1
  python scripts/check_brief_acceptance.py "$OUT/offline_$n" --kind "$kind" $var > "$OUT/offline_$n.check.txt" 2>&1
  echo "$n: $(tail -1 "$OUT/offline_$n.check.txt")"
}
focus() { python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['review_focus'])" "$1"; }
run cheonan_lease reports_evidence/cheonan_lease/input_cheonan_lease.docx "$(focus reports_evidence/cheonan_lease/after/live1/00_run_log.json)" lease "" cheonan_lease
run cjenm_ppl reports_evidence/cjenm_ppl/input_cjenm_ppl.docx "$(focus reports_evidence/cjenm_ppl/after/live_2/00_run_log.json)" ppl "" cjenm_ppl
run freelancer_q4 reports_evidence/freelancer_q4/input_freelancer_q4.pdf "$(focus reports_evidence/freelancer_q4/before/run2/00_run_log.json)" service "" freelancer_q4
wait
for v in v1_renamed_shifted v2_sufficient v3_missing v4_role_reversed; do
  run "lease_$v" "reports_evidence/cheonan_lease/variants/$v.txt" "$(cat reports_evidence/cheonan_lease/variants/${v%%_*}_focus.txt)" lease --variant cheonan_lease
done
wait
