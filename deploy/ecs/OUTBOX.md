# 매출 Outbox 웹·배치 역할 적용 준비 (#22)

이 변경은 ECS task definition을 **생성할 때의 코드·검증**이다. 파일 수정·테스트 통과는 실제 태스크 정의 갱신이나 운영 활성화를 뜻하지 않는다. 기존 수동 CD·이미지 digest·Redis 호환성 게이트를 유지한다.

## 생성하는 역할 설정

`prepare_definition()`은 원본 task definition의 Secret, IAM, 네트워크, DB_URL, TLS command, 기존 프로필·cron을 유지한다. 웹에는 `sales-outbox-web`, 배치에는 `sales-outbox-batch` 프로필을 추가하고 `SALES_OUTBOX_DISPATCH_ENABLED`를 각각 false/true로 설정한다. Backend 설정 이슈는 BE #590이다. 이 프로필은 역할 검증과 기동 시 DB writer 사전 점검을 제공하며, 해당 Backend 코드가 포함된 이미지를 사용해야 한다.

`SALES_OUTBOX_ENABLED`를 새로 추가하거나 false에서 true로 바꾸지 않는다. 기존 true 상태라면 명시적인 `SALES_STORAGE_TYPE=s3`와 버킷 값 또는 Secret 참조가 있어야 한다. 활성화·Dispatcher·프로필 제어를 Secret로 숨겨 값 판단이 불가능하거나, 기존 프로필이 반대 역할이거나, 중복·별칭 설정이 있으면 새 revision 생성 전에 거부한다. 기존 Secret을 읽거나 수정해 우회하지 않는다. rollback은 기록된 revision 자체를 사용하며 새 역할 환경을 덧씌우지 않는다.

S3 버킷 Secret 참조가 있다는 사실만으로 Put/Get/KMS 권한이 검증되지는 않는다. 웹과 배치가 같은 버킷·리전·endpoint·객체 경로를 사용하고 기존 태스크 역할의 권한이 충분한지 확인해야 한다. 원본 파일은 웹 태스크의 개별 임시 디렉터리에 두면 안 된다.

## 읽기 전용 ECS 점검

운영 조회 권한이 있는 Cloud 환경에서 다음을 실행한다. 배포·Secrets 조회·DB 변경·활성화를 수행하지 않고 ECS 서비스와 task definition 메타데이터만 읽는다.

```sh
python3 deploy/ecs/check_outbox_runtime.py --report outbox-runtime-audit.json
```

- 웹2·배치1의 기존 rolling/ALB/Cloud Map 조건, 서비스 안정화와 역할 프로필·Dispatcher 분리를 검사한다.
- 웹과 배치의 Outbox 활성화 모드가 같아야 한다.
- 활성화됐으면 S3 타입과 버킷/DB_URL의 값 또는 Secret 참조가 같아야 한다. 서로 다른 Secret이 같은 값을 가진 경우도 메타데이터만으로 증명할 수 없으므로 보수적으로 실패시켜 별도 검토한다.
- 결과에는 실제 버킷·DB_URL·Secret ARN을 출력하지 않는다.
- `DISABLED`: 비활성 상태이며 역할 설정만 확인. 운영 기능 성공을 뜻하지 않는다.
- `METADATA_PASS`: 메타데이터 조건 통과. `db_route_verified=false`, `s3_access_verified=false`를 유지한다. 실제 업무·권한 검사 전에는 전체 성공으로 표현하지 않는다.
- 현재 태스크가 구버전이고 새 역할 프로필이 없으면 FAIL이 정상이다. 검사기가 자동으로 정규화해 문제를 숨기지 않는다.

## ProxySQL → Router → Primary 확인

현재 저장소 문서는 쓰기 hostgroup 10과 Router→Primary 경로를 설명하지만 실제 ProxySQL/Router 설정 파일은 저장하지 않는다. 애플리케이션 DB_URL을 추측해 새로운 IP/포트로 바꾸지 않는다.

DB 담당자는 기존 관리 경로에서 아래를 **조회만** 하고 결과를 기록한다. 사용자명·호스트는 팀 내부 기록으로 보관하며 비밀번호는 조회하지 않는다.

```sql
-- ProxySQL 관리 인터페이스
SELECT username, default_hostgroup, transaction_persistent FROM runtime_mysql_users;
SELECT hostgroup_id, hostname, port, status FROM runtime_mysql_servers;
SELECT rule_id, active, match_digest, destination_hostgroup, apply FROM runtime_mysql_query_rules;
```

1. 앱 사용자 기본 hostgroup이 현재 writer 경로이고 transaction_persistent=1인지 확인한다.
2. `SELECT ... FOR UPDATE`, Outbox 후보·선행 작업 조회, UTC 시각 조회, 매출·분석 변경이 같은 Primary로 가는지 기존 쿼리 규칙과 통계로 확인한다. SELECT 전체를 Replica로 보내는 포괄 규칙을 적용하지 않는다.
3. Router 목적지가 실제 read_only=0 / super_read_only=0 Primary인지 확인한다. 복제 지연 Replica에 선점 상태 조회를 보내지 않는다.
4. Backend 시작 점검은 한 연결의 READ WRITE 트랜잭션에서 서버 UUID·connection ID와 읽기 전용 상태를 확인한다. 이것만으로 모든 실제 Outbox SQL·다른 풀 연결·장애 전환을 검증했다고 주장하지 않는다.
5. 활성화 전 격리 환경에서 웹2→S3/DB 접수→배치 실행→DONE, 배치 중지 후 복구, 이전 토큰 쓰기 차단을 실제 경로로 확인한다. 운영 DB에 장애를 주입하지 않는다.

## 전환과 복구

공유 원본, 기존 Worker 드레인, Outbox 스키마, 웹/배치 동일 버전·모드를 확인한 뒤 별도 전환한다. 기존 `target=all`은 웹 롤링과 배치 교체를 병행하므로 이 CD 자체로 구버전 혼용 없는 Outbox 활성화를 보장하지 않는다. 최초 Outbox 전환은 접수를 제어하고 기존 작업을 배출하는 절차가 필요하다.

이미 접수한 Outbox 작업이 있을 때 false로 되돌리거나 구버전으로 즉시 rollback하면 작업이 남을 수 있다. 새 접수를 제어하고 작업 배출 또는 호환 배치 유지 방안을 결정한다. 기록과 테이블을 지우지 않는다. Orchestrator 자동 복구 설정도 이 작업에서 변경하지 않는다.

검증 한계: 로컬 단위 테스트와 격리 MySQL 결과를 운영 ECS·ProxySQL·Router·S3 검증으로 대체하지 않는다. AWS CLI/운영 자격 정보가 없는 환경의 조회 실패는 미검증으로 기록한다.
