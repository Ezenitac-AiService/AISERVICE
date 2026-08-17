# DuckDNS DDNS 설정

이 폴더는 Windows PowerShell과 작업 스케줄러를 사용해 `ezenitac.duckdns.org`의 공인 IP를 5분마다 DuckDNS에 갱신합니다.

## 구성 파일

- `Install-DuckDns.ps1`: 토큰 입력, 즉시 연결 테스트, 5분 주기 작업 등록
- `Set-DuckDnsConfig.ps1`: 토큰을 현재 Windows 사용자 계정에 종속된 DPAPI 암호문으로 저장
- `Update-DuckDns.ps1`: DuckDNS 갱신 요청 및 `duckdns.log` 기록
- `run-duckdns.bat`: 수동 갱신용 배치 파일
- `Uninstall-DuckDns.ps1`: 예약 작업 삭제
- `.env`: `token=...` 형식의 로컬 토큰 파일(저장소에 커밋하지 않음)
- `duckdns-config.xml`: 설치 후 생성되는 로컬 비밀 설정 파일(저장소에 커밋하지 않음)
- `duckdns.log`: 갱신 결과 로그(저장소에 커밋하지 않음)

## 최초 설정

일반 PowerShell 창에서 `C:\AISERVICE\ddns`로 이동한 뒤 실행합니다.

```powershell
cd C:\AISERVICE\ddns
Set-ExecutionPolicy -Scope Process Bypass
.\Install-DuckDns.ps1 -Domain ezenitac
```

`ddns\.env`에 `token=발급받은토큰`이 있으면 그 값을 우선 사용합니다. `.env`가 없을 때만 실행 중 토큰을 입력하며, 입력 내용은 화면에 표시되지 않습니다. 설치가 끝나면 즉시 한 번 갱신하고, 현재 로그인한 Windows 계정의 작업 스케줄러에 5분 주기 작업을 등록합니다.

선택적으로 `.env`에 도메인도 지정할 수 있습니다.

```text
token=발급받은토큰
domain=ezenitac
```

이미 설정 파일이 있으면 기존 토큰을 재사용합니다. `ConvertTo-SecureString` 또는 DPAPI 복호화 오류가 나오면 토큰을 입력했던 동일한 Windows 계정의 PowerShell에서 다음처럼 설정을 다시 저장합니다.

```powershell
.\Install-DuckDns.ps1 -Domain ezenitac -ResetConfig
```

토큰은 스크립트에 평문으로 넣지 않습니다. `duckdns-config.xml`에는 현재 Windows 사용자만 복호화할 수 있는 DPAPI 형식으로 저장됩니다. 다른 계정(특히 `SYSTEM`)으로 갱신 스크립트를 실행하면 토큰을 복호화할 수 없습니다.

토큰을 공개 채팅, 로그 또는 저장소에 노출했다면 DuckDNS에서 토큰을 재발급한 뒤 새 토큰을 사용하세요.

## 확인

```powershell
Get-Content .\duckdns.log -Tail 20
Get-ScheduledTask -TaskName DuckDNS-ezenitac-Update
Resolve-DnsName ezenitac.duckdns.org
```

로그에 `Update succeeded`와 `result=OK`가 기록되면 DuckDNS 갱신은 정상입니다. 수동으로 다시 실행하려면 다음을 사용합니다.

```powershell
.\run-duckdns.bat
```

## 제거

예약 작업만 제거:

```powershell
.\Uninstall-DuckDns.ps1
```

예약 작업과 로컬 암호화 설정까지 제거:

```powershell
.\Uninstall-DuckDns.ps1 -RemoveConfig
```

## 라우터와 Windows 방화벽

DuckDNS는 도메인을 현재 공인 IP에 연결할 뿐이며, 컴퓨터의 서비스 포트를 자동으로 열어 주지는 않습니다. 외부에서 AISERVICE를 접속하려면 별도로 다음을 설정해야 합니다.

1. 라우터에서 외부 포트를 내부 컴퓨터의 서비스 포트로 포트 포워딩합니다.
2. Windows Defender 방화벽에서 해당 인바운드 포트를 허용합니다.
3. 외부 네트워크(예: 휴대폰 테더링)에서 `https://ezenitac.duckdns.org:<외부포트>`로 테스트합니다.

공인 IP가 바뀌어도 DDNS 이름이 새 IP를 가리키는 것과, 라우터/방화벽에서 실제 서비스가 외부에 노출되는 것은 별개의 설정입니다. 필요한 서비스 포트만 열고 관리자 페이지나 데이터베이스 포트는 인터넷에 직접 노출하지 않는 것을 권장합니다.
