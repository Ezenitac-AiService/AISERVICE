# Green service environment allowlists

서비스는 공용 `bteam/.env`를 mount하지 않는다. 운영 secret은 Compose secret 또는 외부
secret manager에서 서비스별로 주입한다.

| service | permitted configuration keys |
| --- | --- |
| `pipeline_runner` | `APP_RUN_MODE`, `DEPLOYMENT_STAGE`, `MYSQL_WRITE_ENDPOINT`, `REDIS_ENDPOINT`, `CHROMA_WRITE_ENDPOINT`, `GATEWAY_ENDPOINTS` |
| `dashboard_backend` | `APP_RUN_MODE`, `DEPLOYMENT_STAGE`, `MYSQL_READ_ENDPOINT`, `REDIS_ENDPOINT` |
| `chatbot_a` | `APP_RUN_MODE`, `DEPLOYMENT_STAGE`, `MYSQL_READ_ENDPOINT`, `REDIS_ENDPOINT`, `CHROMA_READ_ENDPOINT`, `GATEWAY_ENDPOINTS` |
| `chatbot_b` | `APP_RUN_MODE`, `DEPLOYMENT_STAGE`, `MYSQL_READ_ENDPOINT`, `REDIS_ENDPOINT`, `CHROMA_READ_ENDPOINT`, `GATEWAY_ENDPOINTS` |

`DB_PASSWORD`, bearer token, SMTP password 등 값은 로그·inventory·manifest에 기록하지
않는다. 기존 Blue `.env`는 Green build context 및 컨테이너에 전달하지 않는다.

