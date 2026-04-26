# 10. 로컬 실행 가이드 (Rules MVP)

## 1) 사전 조건
- Python 3.10+ (현재 환경은 3.14.x)
- 작업 경로:
  - `c:\Users\FURSYS\Desktop\aouribot\aouri-bot`

## 2) rules 파일 위치
- 런타임 탑재본:
  - `aouri-bot/runtime/resources/review_rules_master.json`
- 업데이트 시(수동):
```powershell
Copy-Item -Force "..\docs\review_output\04_review_rules_master.json" ".\runtime\resources\review_rules_master.json"
```

## 3) 서버 실행
```bash
cd aouri-bot
python -m runtime.app
```

실행 후 접속:
- Admin UI: [http://127.0.0.1:8787/admin](http://127.0.0.1:8787/admin)
- Review Results UI: [http://127.0.0.1:8787/admin/reviews](http://127.0.0.1:8787/admin/reviews)
- Approval Queue UI: [http://127.0.0.1:8787/admin/approval](http://127.0.0.1:8787/admin/approval)
- Upload & Review: [http://127.0.0.1:8787/upload](http://127.0.0.1:8787/upload)
- EP Mock (법무검토신청): [http://127.0.0.1:8787/ep/mock/legal_request](http://127.0.0.1:8787/ep/mock/legal_request)
- Health: [http://127.0.0.1:8787/health](http://127.0.0.1:8787/health)

## 4) API 사용 예시
### rules 조회
```bash
curl "http://127.0.0.1:8787/api/rules?status=approval_required&entity=퍼시스&contract_type=대리점/위탁/유통"
```

### backlog 조회(참고용)
```bash
curl "http://127.0.0.1:8787/api/backlog"
```

### analyze 호출
```bash
curl -X POST "http://127.0.0.1:8787/api/review/analyze" ^
  -H "Content-Type: application/json" ^
  -d "{\"entity\":\"퍼시스\",\"contract_type\":\"물품공급/구매/매매\",\"text\":\"without limitation 책임 및 indemnify 조항\"}"
```

## 5) 테스트 실행
```bash
cd aouri-bot
python -m unittest discover -s runtime/tests -v
```

## 6) 운영 정책(중요)
- 판정 로직 사용 대상:
  - `confirmed_standard`
  - `confirmed_pattern`
  - `exception_possible`
  - `approval_required`
- `unconfirmed_backlog`는 **참고용 조회만 가능**하며 판정에 사용하지 않음
