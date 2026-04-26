# 19. 통합 테스트 요약 (업로드 → analyze → DB 저장 → 관리자 조회)

## 1) 목적
- 단일 단위 테스트 외에, 실제 MVP 사용 흐름을 연결해 검증한다.

## 2) 최소 시나리오
1. 샘플 계약 텍스트 업로드(사용자 entity/contract_type 미입력)
2. 질문 세션 생성 확인
3. 답변 저장 후 review 실행
4. DB 저장된 결과 조회(목록/상세)
5. high risk 또는 approval queue 등록 여부 확인

## 3) 테스트 코드
- 파일: `aouri-bot/runtime/tests/test_integration_flow.py`
- 검증 포인트:
  - `/api/upload` → `question_session_id` 반환
  - `/api/question_sessions/{id}/review` → `request_id` 반환 및 review 포함
  - `/api/reviews` 조회 가능
  - `/api/reviews/{request_id}` 상세에서 `rules_version/applied_rules` 존재
  - `/api/approval_queue?status=new` 목록에 포함

## 4) 실행 방법
```bash
cd aouri-bot
python -m unittest discover -s runtime/tests -v
```

