#!/usr/bin/env bash
# B. 기본 CloudWatch 알람 (CloudShell에서 실행). 기준값은 임시값입니다.
set -euo pipefail
export AWS_PAGER=""
TOPIC_ARN=arn:aws:sns:ap-northeast-2:613538400341:memme-v2-alerts
LB=app/memme-v2-alb/e8dd35982688eba9
TG=targetgroup/memme-backend-v2/857e4e0050333092
put() { aws cloudwatch put-metric-alarm --alarm-actions $TOPIC_ARN --ok-actions $TOPIC_ARN --tags Key=Project,Value=memme-v2 "$@"; echo "ok $2"; }

put --alarm-name memme-v2-alb-healthy-lt-2 --alarm-description "정상 웹 서버 수 2 미만 (2분 연속)" \
  --namespace AWS/ApplicationELB --metric-name HealthyHostCount \
  --dimensions Name=LoadBalancer,Value=$LB Name=TargetGroup,Value=$TG \
  --statistic Minimum --period 60 --evaluation-periods 2 --threshold 2 --comparison-operator LessThanThreshold --treat-missing-data missing
put --alarm-name memme-v2-alb-healthy-zero --alarm-description "정상 웹 서버 0개 = 서비스 전체 중단 (1분)" \
  --namespace AWS/ApplicationELB --metric-name HealthyHostCount \
  --dimensions Name=LoadBalancer,Value=$LB Name=TargetGroup,Value=$TG \
  --statistic Maximum --period 60 --evaluation-periods 1 --threshold 1 --comparison-operator LessThanThreshold --treat-missing-data missing
put --alarm-name memme-v2-alb-elb-5xx --alarm-description "ALB 자체 5xx(502/503/504) 5분 10건 이상" \
  --namespace AWS/ApplicationELB --metric-name HTTPCode_ELB_5XX_Count --dimensions Name=LoadBalancer,Value=$LB \
  --statistic Sum --period 300 --evaluation-periods 1 --threshold 10 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching
put --alarm-name memme-v2-backend-5xx --alarm-description "백엔드 응답 5xx 5분 10건 이상" \
  --namespace AWS/ApplicationELB --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value=$LB Name=TargetGroup,Value=$TG \
  --statistic Sum --period 300 --evaluation-periods 1 --threshold 10 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching
put --alarm-name memme-v2-backend-latency-p95 --alarm-description "백엔드 응답 시간 p95 3초 초과 (5분)" \
  --namespace AWS/ApplicationELB --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=$LB Name=TargetGroup,Value=$TG \
  --extended-statistic p95 --period 300 --evaluation-periods 1 --threshold 3 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching

for pair in "i-06c4c159ed4155c70:ai-10.0.1.236" "i-096b3f8f8553bb213:db-10.0.11.185" "i-056877f91d647a899:db-10.0.11.65" "i-038258fbf958879f2:dbcontrol-10.0.11.9"; do
  id=${pair%%:*}; nm=${pair#*:}
  put --alarm-name memme-v2-ec2-$nm-status --alarm-description "EC2 $nm($id) 상태 검사 실패 (2분 연속, 데이터 없음도 실패)" \
    --namespace AWS/EC2 --metric-name StatusCheckFailed --dimensions Name=InstanceId,Value=$id \
    --statistic Maximum --period 60 --evaluation-periods 2 --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data breaching
done

put --alarm-name memme-v2-redis-memory --alarm-description "Redis 세션 메모리 사용률 80% 초과" \
  --namespace AWS/ElastiCache --metric-name DatabaseMemoryUsagePercentage --dimensions Name=CacheClusterId,Value=memme-prod-session-v2-001 \
  --statistic Maximum --period 300 --evaluation-periods 1 --threshold 80 --comparison-operator GreaterThanThreshold --treat-missing-data missing
put --alarm-name memme-v2-redis-evictions --alarm-description "Redis eviction 발생 = 로그인 세션 삭제 시작" \
  --namespace AWS/ElastiCache --metric-name Evictions --dimensions Name=CacheClusterId,Value=memme-prod-session-v2-001 \
  --statistic Sum --period 300 --evaluation-periods 1 --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching
echo "B done"
aws cloudwatch describe-alarms --alarm-name-prefix memme-v2- --query 'MetricAlarms[].[AlarmName,StateValue]' --output text
