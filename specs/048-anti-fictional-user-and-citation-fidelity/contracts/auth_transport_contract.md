# Chat Authentication and Rate-Limit Transport Contract

## 적용 범위

- ChatA와 ChatB의 브라우저 요청 및 machine-to-machine/direct API 요청에 적용한다.
- 인증 성공 결과는 공통 `principal_id`와 `service_id`로 정규화한다.
- HTML, JavaScript, localStorage 및 sessionStorage에는 Bearer credential 또는 session 원문을 저장하지 않는다.

## 브라우저 흐름

1. 동일 출처의 인증 endpoint가 예측 불가능한 opaque session identifier를 발급한다.
2. session cookie는 `Secure`, `HttpOnly`, `SameSite=Lax`, 제한된 `Path`, Settings 기반 TTL을 사용한다.
3. 상태 변경 요청은 cookie와 별개의 요청별 CSRF token을 Settings 지정 header로 제출하고 서버에서 session과 결속해 검증한다.
4. JavaScript는 session identifier나 내부 Bearer credential을 읽거나 전달하지 않는다.
5. session 누락·만료는 `401`, CSRF 누락·불일치는 `403`으로 fail-closed 처리한다.

## Direct API 흐름

1. `Authorization: Bearer <credential>`을 사용한다.
2. validator와 credential material이 아닌 secret reference는 Settings에서 주입한다.
3. 누락·오류·만료 credential은 `401`로 처리한다.

## 분산 Rate Limit 및 Concurrency

- key는 `feature048:limit:{service_id}:{principal_id}` 형식을 사용하되 실제 prefix는 Settings에서 주입한다.
- 모든 worker는 동일 Redis endpoint를 사용한다.
- 요청 카운터와 TTL 설정은 Lua script 또는 동등한 단일 atomic operation으로 처리한다.
- concurrency lease에는 owner와 만료 TTL을 두어 worker 비정상 종료 시 영구 점유를 방지한다.
- PRODUCTION에서 Redis 연결·원자 연산 실패 시 요청을 실행하지 않고 retry 가능한 `503`/`UPSTREAM_ERROR`로 fail-closed 처리한다.
- 로그에는 principal/session/token 원문 대신 비가역 상관 식별자만 기록한다.

## Client Request와 Server Cap

- `effective_timeout_ms = min(client_timeout_ms, settings_timeout_ms)`
- `effective_max_output_tokens = min(client_max_output_tokens, settings_output_token_cap)`
- client 값이 없으면 Settings 값을 사용한다.
- 유효 범위를 벗어난 client 값은 `INVALID_REQUEST`로 거부한다.

