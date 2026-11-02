#!/usr/bin/env bash
# 사업팀 전달본 실제 AI 검증 — 떠 있는 서버(8787, 작업 스케줄러)에 새 세션으로 업로드→검토→다운로드 후 판정.
# Usage: bash scripts/run_brief_live.sh NAME CASE KIND [OUT]
set -u
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
n=$1; case_=$2; kind=$3; OUT=${4:-reports_evidence/business_brief/after}
case $case_ in
  cheonan_lease) f=reports_evidence/cheonan_lease/input_cheonan_lease.docx; lg=reports_evidence/cheonan_lease/after/live1/00_run_log.json;;
  cjenm_ppl) f=reports_evidence/cjenm_ppl/input_cjenm_ppl.docx; lg=reports_evidence/cjenm_ppl/after/live_2/00_run_log.json;;
  freelancer_q4) f=reports_evidence/freelancer_q4/input_freelancer_q4.pdf; lg=reports_evidence/freelancer_q4/before/run2/00_run_log.json;;
esac
rf=$(python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['review_focus'])" "$lg")
rm -rf "$OUT/$n"
python scripts/e2e_upload_review_download.py --input "$f" --out-dir "$OUT/$n" --review-focus "$rf" \
  --answers "reports_evidence/$case_/config/answers.json" > "$OUT/$n.log" 2>&1
python scripts/run_texts.py "$OUT/$n" >> "$OUT/$n.log" 2>&1
python scripts/check_brief_acceptance.py "$OUT/$n" --kind "$kind" > "$OUT/$n.check.txt" 2>&1
echo "$n: $(tail -1 "$OUT/$n.check.txt")"
