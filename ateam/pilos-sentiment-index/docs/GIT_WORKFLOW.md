# Git 작업 규칙

> 정본 범위: 브랜치 운영, 커밋, Pull Request, 문서 최신화와 작업 브랜치 동기화
>
> 상태: 현재 기준
>
> 최초 적용일: 2026-07-22
>
> 마지막 갱신: 2026-08-04

---

# 1. 운영 목적

이 문서는 팀원이 같은 방식으로 Git을 사용하기 위한 공통 규칙입니다.

Git 규칙의 목적은 절차를 복잡하게 만드는 것이 아니라 다음 문제를 줄이는 데 있습니다.

- 다른 팀원의 작업을 덮어쓰는 문제
- 작업 중인 코드가 기준 브랜치에 바로 반영되는 문제
- 브랜치마다 문서와 공통 구조가 달라지는 문제
- 커밋만 보고 변경 목적을 알기 어려운 문제
- 충돌이 발생했을 때 변경 책임을 찾기 어려운 문제

프로젝트 규모와 팀 숙련도를 고려하여 필요한 규칙만 사용합니다.

불필요한 브랜치와 승인 절차를 늘리기보다, 기능 작업과 공통 기준 변경을 구분하는 데 집중합니다.

---

# 2. 기본 브랜치

프로젝트는 다음 두 개의 공통 브랜치를 사용합니다.

| 브랜치 | 역할 |
|---|---|
| main | 발표·배포 가능한 안정 버전 |
| develop | 팀의 최신 통합 개발 기준 |

---

## main

`main`은 발표하거나 배포할 수 있는 안정된 상태를 유지합니다.

일반적인 기능 작업은 `main`에서 직접 진행하지 않습니다.

`develop`에서 통합과 확인이 끝난 버전만 `main`에 반영합니다.

---

## develop

`develop`은 팀원이 기능 브랜치를 만들 때 기준으로 사용하는 브랜치입니다.

완료된 기능은 Pull Request를 통해 `develop`에 병합합니다.

다음 내용은 `develop`을 기준으로 공유합니다.

- 최신 공통 폴더 구조
- 최신 프로젝트 문서
- 통합이 완료된 기능
- 공통 설정 파일
- 팀원이 새 작업을 시작할 때 필요한 기준 코드

`develop`에서는 일반적인 기능을 직접 구현하지 않습니다.

다만 팀장이 관리하는 공통 문서 최신화와 최소 공통 구조 변경은 예외로 합니다.

---

# 3. 작업 브랜치

기능 구현과 오류 수정은 목적에 맞는 작업 브랜치에서 진행합니다.

| 접두어 | 용도 | 예시 |
|---|---|---|
| feature/ | 새로운 기능 구현 | feature/comment-preprocessing |
| fix/ | 오류 수정 | fix/empty-comment-filter |
| refactor/ | 동작을 유지하는 구조 개선 | refactor/storage-responsibility |
| test/ | 테스트 코드 작성 | test/preprocess-pipeline |
| chore/ | 설정·의존성·공통 구조 작업 | chore/add-jobs-package |
| docs/ | 별도 검토가 필요한 문서 작업 | docs/update-data-contract |

브랜치 이름은 작업 목적을 알 수 있도록 작성합니다.

```text
feature/direction-intensity-baseline
fix/comment-created-at
refactor/preprocess-pipeline
```

개인의 이름이나 의미가 불분명한 이름은 사용하지 않습니다.

```text
kwang-work
test1
new
final
```

---

# 4. 기능 작업 흐름

새로운 기능 작업은 최신 `develop`에서 시작합니다.

```bash
git switch develop
git pull --ff-only origin develop
```

작업 브랜치를 생성합니다.

```bash
git switch -c feature/comment-preprocessing
```

작업 내용을 확인합니다.

```bash
git status
git diff
```

공개 입력·출력, 실행 흐름이나 실패·재실행 계약이 있는 기능은 구현과 함께
관련 `specs/*.md`를 작성하거나 갱신합니다. 작성 형식과 상태 구분은
`specs/README.md`를 따릅니다.

변경 파일을 추가하고 커밋합니다.

```bash
git add <파일>
git commit -m "feat: 댓글 전처리 기능 추가"
```

원격 브랜치에 처음 Push할 때는 다음 명령을 사용합니다.

```bash
git push -u origin feature/comment-preprocessing
```

이후에는 다음 명령만 사용해도 됩니다.

```bash
git push
```

작업이 완료되면 Pull Request를 생성하여 `develop`에 병합합니다.

```text
feature/*
    ↓
Pull Request
    ↓
develop
```

---

# 5. 기능 브랜치에 최신 develop 반영

작업 중 다른 기능이나 공통 문서가 `develop`에 반영되었다면 작업 브랜치도 최신화합니다.

먼저 원격 변경 사항을 가져옵니다.

```bash
git fetch origin
```

현재 작업 브랜치에서 최신 `origin/develop`을 병합합니다.

```bash
git merge origin/develop
```

필요하면 병합 목적을 알 수 있는 메시지를 사용합니다.

```text
merge: develop 최신 변경사항 반영
```

문서와 공통 구조 변경이 중심이라면 다음과 같이 작성할 수 있습니다.

```text
merge: develop 문서 및 구조 최신화 반영
```

작업 브랜치에서는 다음 명령을 사용하지 않습니다.

```bash
git pull --ff-only origin develop
```

`--ff-only`는 현재 브랜치와 원격 브랜치가 같은 흐름에 있을 때만 병합할 수 있습니다.

이미 기능 커밋이 존재하는 작업 브랜치와 `develop`은 서로 갈라진 상태이므로 대부분 실패합니다.

`--ff-only`는 로컬 `develop`을 최신화할 때 사용합니다.

```bash
git switch develop
git pull --ff-only origin develop
```

---

# 6. 문서 최신화

프로젝트 공통 문서는 팀장이 정본을 관리합니다.

대상은 다음과 같습니다.

- README.md
- AGENTS.md
- docs/*.md
- 팀 공통 개발 규칙
- 프로젝트 구조와 데이터 계약
- 합의된 의사결정 기록

회의에서 이미 합의된 내용을 반영하거나 현재 구현 상태에 맞게 문서를 최신화하는 작업은 팀장이 `develop`에서 직접 진행할 수 있습니다.

예시

- 오탈자 수정
- 합의된 책임 구조 반영
- 현재 폴더 구조 갱신
- 명령어와 경로 수정
- 문서 간 표현 통일
- 완료된 구현 내용 반영
- 팀 규칙 최신화

문서 최신화는 일반적인 기능 구현과 구분합니다.

```text
팀 합의
    ↓
팀장이 develop 문서 갱신
    ↓
docs 커밋
    ↓
origin/develop Push
```

예시

```bash
git switch develop
git pull --ff-only origin develop

git add docs/ARCHITECTURE.md
git commit -m "docs: 분석 파이프라인 책임 구조 최신화"
git push origin develop
```

---

## 별도 브랜치를 사용하는 문서 작업

다음 경우에는 문서 작업이라도 별도 브랜치를 사용합니다.

- 아직 팀에서 합의되지 않은 구조를 제안하는 경우
- 여러 팀원의 검토가 필요한 대규모 변경
- 문서와 기능 구현이 함께 변경되는 경우
- 데이터 계약 변경과 실제 코드 수정이 함께 진행되는 경우
- 문서 변경이 기존 작업에 큰 영향을 주는 경우
- 팀장이 아닌 팀원이 공통 문서를 수정하는 경우

예시

```text
docs/revise-data-contract
refactor/storage-interface
chore/repository-layout
```

팀원은 공통 문서 수정이 필요하면 먼저 팀장에게 알립니다.

팀장이 요청하거나 수정 범위를 합의한 경우에만 공통 문서를 직접 수정합니다.

---

# 7. 공통 구조 변경

빈 패키지 추가, 공통 설정 파일 추가 등 모든 팀원이 공유해야 하는 최소 구조는 팀장이 `develop`에서 직접 반영할 수 있습니다.

예시

```text
pilos/jobs/__init__.py
docs/ARCHITECTURE.md
```

단순 문서 변경과 공통 구조 추가는 커밋을 나누어 기록하는 것을 권장합니다.

```bash
git commit -m "docs: 실행 영역 책임과 구조 최신화"
git commit -m "chore: jobs 실행 영역 패키지 추가"
```

다음 작업은 공통 구조 변경이 아니라 기능 구현으로 봅니다.

- 전처리 로직 이동
- 토크나이저 구현
- 저장 로직 구현
- 모델 학습 코드 구현
- 기존 모듈의 대규모 리팩터링
- 실제 실행 파이프라인 구현

이러한 작업은 목적에 맞는 작업 브랜치에서 진행합니다.

---

# 8. 커밋 규칙

커밋 메시지는 다음 형식을 사용합니다.

```text
<type>: <변경 내용>
```

예시

```text
feat: 댓글 전처리 기능 추가
fix: 빈 댓글 제거 조건 수정
refactor: JSON 저장 책임을 storage로 이동
docs: 분석 파이프라인 구조 최신화
test: 전처리 결측값 테스트 추가
chore: Kiwi 의존성 추가
```

사용하는 커밋 타입은 다음과 같습니다.

| 타입 | 의미 |
|---|---|
| feat | 새로운 기능 |
| fix | 오류 수정 |
| refactor | 동작을 유지하는 코드 구조 개선 |
| docs | 문서 변경 |
| test | 자동화 테스트·검증 스크립트와 재현 가능한 검증 조건 추가·수정 |
| chore | 개발 설정, 의존성, 실험 파라미터와 비기능 실행 설정 변경 |
| style | 코드 동작과 관계없는 형식 수정 |

커밋 메시지는 변경한 파일명이 아니라 변경 목적을 설명합니다.

`test`는 다음 변경에 사용합니다.

- 자동화 테스트 코드 추가·수정
- 검증 스크립트 추가·수정
- 검증 로직 변경
- 재현 가능한 테스트 조건 변경

코드를 수동으로 실행했다는 사실만으로 `test`를 사용하지 않습니다.

`chore`는 다음 변경에 사용합니다.

- 개발 설정 변경
- 실험 파라미터 변경
- 의존성·환경 변경
- 실행에 필요한 비기능 설정 변경

예시

```text
chore: TF-IDF ngram 범위 실험값 변경
chore: TF-IDF min_df 실험값 조정
```

분석 기능 자체를 새로 구현하면 `feat`, 기존 동작의 오류를 수정하면 `fix`를 사용합니다.

좋은 예시

```text
refactor: 댓글 수집과 원본 저장 책임 분리
```

피해야 하는 예시

```text
comment.py 수정
수정
최종
진짜최종
```

---

# 9. 커밋 범위

하나의 커밋에는 하나의 목적을 담습니다.

전처리 기능과 문서 수정이 함께 필요하더라도 가능하면 커밋을 분리합니다.

```text
feat: 댓글 전처리 기능 추가
docs: 댓글 전처리 흐름 문서 반영
```

다음과 같이 서로 관계없는 변경을 하나의 커밋에 섞지 않습니다.

```text
전처리 수정
README 수정
CSS 수정
의존성 추가
```

작업 중 변경이 섞였다면 파일 또는 변경 영역을 나누어 추가합니다.

```bash
git add pilos/analysis/preprocessing.py
git commit -m "refactor: 댓글 전처리 책임 분리"

git add docs/ARCHITECTURE.md
git commit -m "docs: 전처리 책임 구조 반영"
```

---

# 10. Pull Request

기능 브랜치는 Pull Request를 통해 `develop`에 병합합니다.

Pull Request에는 다음 내용을 작성합니다.

- 무엇을 변경했는가
- 왜 변경했는가
- 어떻게 확인했는가
- 다른 팀원이 알아야 할 내용이 있는가
- 관련 기능 명세의 구현·검증·통합 상태가 현재 브랜치와 일치하는가

예시

```md
## 변경 내용

- 댓글 JSONL 로드 기능 추가
- 댓글 전처리 함수 분리
- 종목코드의 A 접두사 제거
- 빈 텍스트와 중복 comment_id 제거

## 변경 이유

수집 원본과 전처리 책임을 분리하고,
후속 토큰화 단계에서 동일한 전처리 결과를 사용하기 위함입니다.

## 확인 내용

- 샘플 JSONL 로드 확인
- 전처리 후 행 수 확인
- created_at과 updated_at 형식 확인
```

Pull Request의 제목도 커밋 메시지와 비슷한 형식을 사용합니다.

```text
feat: 댓글 전처리 파이프라인 구현
```

---

# 11. 병합 전 확인

Pull Request를 병합하기 전에 다음 내용을 확인합니다.

- 작업 브랜치가 최신 `develop`을 반영했는가
- 실행 오류가 없는가
- 관련 없는 파일이 포함되지 않았는가
- 임시 파일이나 개인 데이터가 포함되지 않았는가
- `.env`가 포함되지 않았는가
- 대용량 데이터 파일이 포함되지 않았는가
- 문서 변경이 필요하면 함께 반영했는가
- 관련 기능의 `specs` 문서가 구현·검증 상태를 반영하는가
- 커밋 메시지만 보고 변경 목적을 이해할 수 있는가

---

# 12. 데이터 파일과 추적 관리

원본 데이터, 중간 산출물, 모델 파일 등은 Git에서 관리할 필요가 있는지 먼저 확인합니다.

일반적으로 다음 파일은 Git 추적 대상에서 제외합니다.

- 개인 환경변수 파일
- 가상환경
- 캐시 파일
- 대용량 원본 데이터
- 실행 중 생성되는 중간 산출물
- 로컬 전용 모델 파일
- 개인 Notebook 체크포인트

이미 Git이 추적 중인 파일은 `.gitignore`에 추가하는 것만으로 추적이 중단되지 않습니다.

파일은 로컬에 유지하고 Git 추적만 제거하려면 다음 명령을 사용합니다.

```bash
git rm --cached <파일>
```

폴더 전체의 추적을 제거하려면 다음과 같이 사용합니다.

```bash
git rm -r --cached <폴더>
```

삭제 또는 추적 제외 전에는 해당 파일이 팀 공통 자산인지 반드시 확인합니다.

특정 실수로 추가된 파일 하나 때문에 지나치게 넓은 확장자 규칙을 추가하지 않습니다.

예를 들어 CSV 전체를 제외할 필요가 없다면 다음과 같이 모든 CSV를 무조건 제외하지 않습니다.

```gitignore
*.csv
```

대신 실제로 추적하지 않을 경로나 파일을 구체적으로 관리합니다.

```gitignore
data/raw/
data/processed/
```

---

# 13. 충돌 처리

병합 중 충돌이 발생하면 자동으로 내용을 선택하지 않습니다.

충돌 파일을 확인합니다.

```bash
git status
```

충돌 표시를 확인하고 필요한 내용을 직접 정리합니다.

```text
<<<<<<< HEAD
현재 브랜치 내용
=======
병합하려는 브랜치 내용
>>>>>>> origin/develop
```

충돌을 해결한 뒤 파일을 추가합니다.

```bash
git add <충돌 해결 파일>
```

병합을 완료합니다.

```bash
git commit
```

다른 팀원의 코드나 공통 문서에서 충돌이 발생했고 어느 내용을 유지해야 할지 확실하지 않다면 해당 담당자 또는 팀장과 확인합니다.

---

# 14. 금지 사항

다음 작업은 원칙적으로 하지 않습니다.

- `main`에서 직접 기능 구현
- `develop`에서 일반 기능 구현
- 다른 팀원의 작업 브랜치에 직접 Push
- 확인하지 않은 강제 Push
- `.env` 커밋
- 가상환경 커밋
- 대용량 원본 데이터 무단 커밋
- 의미 없는 커밋 메시지 사용
- 충돌 내용을 확인하지 않고 임의 선택
- 여러 목적의 작업을 하나의 거대한 커밋으로 기록
- 합의되지 않은 공통 문서를 임의로 수정

강제 Push가 반드시 필요한 상황이라면 팀장과 먼저 확인합니다.

```bash
git push --force
```

공유 브랜치에는 위 명령을 사용하지 않습니다.

---

# 15. 자주 사용하는 명령

## develop 최신화

```bash
git switch develop
git pull --ff-only origin develop
```

## 새 기능 브랜치 생성

```bash
git switch -c feature/<작업명>
```

## 현재 상태 확인

```bash
git status
git diff
```

## 커밋

```bash
git add <파일>
git commit -m "feat: 변경 내용"
```

## 첫 Push

```bash
git push -u origin <브랜치명>
```

## 이후 Push

```bash
git push
```

## 작업 브랜치에 최신 develop 반영

```bash
git fetch origin
git merge origin/develop
```

## 브랜치 목록 확인

```bash
git branch
git branch -a
```

## 최근 커밋 확인

```bash
git log --oneline --graph --decorate --all
```

---

# 16. 판단이 어려운 경우

다음 사항이 확실하지 않다면 변경 전에 팀장과 확인합니다.

- 어느 폴더에 파일을 만들어야 하는가
- 공통 문서를 직접 수정해도 되는가
- 데이터 파일을 Git에 포함해야 하는가
- 기존 구조를 변경해도 되는가
- 작업 브랜치를 새로 만들어야 하는가
- 충돌에서 어느 내용을 유지해야 하는가
- 공통 브랜치에 직접 반영해도 되는가

규칙의 목적은 작업을 막는 것이 아니라 팀원의 변경이 서로 충돌하지 않도록 하는 것입니다.
