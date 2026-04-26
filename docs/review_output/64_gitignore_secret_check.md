# .gitignore 민감정보 점검/보강

## 목표
- 로컬 키/비밀 파일이 Git에 올라가지 않도록 기본 패턴을 포함

## 반영 내용
- `.env.*.local` 추가
- `secrets.json` 추가
- `*.pem`, `*.key` 추가

## 수정 파일
- [.gitignore](file:///c:/Users/FURSYS/Desktop/aouribot/.gitignore)

## 주의(이미 추적 중인 파일)
- `.gitignore`를 추가해도 **이미 Git이 추적 중인 파일은 자동으로 제외되지 않는다.**
- 아래 파일들이 `git ls-files`에 잡힌다면 수동으로 추적 해제/삭제가 필요하다:
  - `.env`, `.env.local`, `.env.*.local`, `secrets.json`, `*.pem`, `*.key`

