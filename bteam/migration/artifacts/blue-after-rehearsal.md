# Blue after Green candidate rehearsal

후속 확인은 read-only로 수행했다. Blue 컨테이너는 다음과 같이 계속 `Up` 상태였고,
`bteam_db`와 `aiservice-redis`는 healthy였다.

- `bteam_db`
- `oliview_backend`
- `oliview_frontend`
- `oliview_chatbot_a`
- `oliview_chatbot_b`
- `aiservice-gateway`
- `aiservice-redis`

candidate direct health 결과는 `candidate-health.json`에 보존한다. Blue active gateway의
HTTP probe는 HTTP→HTTPS redirect 후 로컬 인증서/경로 응답이 404였으므로, 이 artifact는
Blue 외부 health 합격을 주장하지 않는다. 운영 cutover 전 실제 외부 health endpoint와
인증서 chain을 operator가 재확인해야 한다.

`blue_mutated=false`; Blue container/network/volume/active upstream을 변경하지 않았다.

