#!/usr/bin/env bash
# A(이메일판). SNS 토픽 + ECS 태스크 중지 이벤트. IAM 역할·Lambda 없음 (CloudShell에서 실행)
set -euo pipefail
export AWS_PAGER=""
ACC=613538400341; R=ap-northeast-2
TAG="Key=Project,Value=memme-v2"
TOPIC_ARN=$(aws sns create-topic --name memme-v2-alerts --tags $TAG --query TopicArn --output text)
echo "topic $TOPIC_ARN"
POLICY=$(cat <<JSON
{"Version":"2012-10-17","Statement":[
 {"Sid":"Owner","Effect":"Allow","Principal":{"AWS":"*"},"Action":["SNS:Publish","SNS:Subscribe","SNS:GetTopicAttributes","SNS:SetTopicAttributes","SNS:ListSubscriptionsByTopic"],"Resource":"$TOPIC_ARN","Condition":{"StringEquals":{"AWS:SourceOwner":"$ACC"}}},
 {"Sid":"CloudWatchAlarms","Effect":"Allow","Principal":{"Service":"cloudwatch.amazonaws.com"},"Action":"SNS:Publish","Resource":"$TOPIC_ARN","Condition":{"StringEquals":{"AWS:SourceAccount":"$ACC"}}},
 {"Sid":"EventBridge","Effect":"Allow","Principal":{"Service":"events.amazonaws.com"},"Action":"SNS:Publish","Resource":"$TOPIC_ARN","Condition":{"StringEquals":{"AWS:SourceAccount":"$ACC"}}}
]}
JSON
)
aws sns set-topic-attributes --topic-arn "$TOPIC_ARN" --attribute-name Policy --attribute-value "$POLICY"
PATTERN="{\"source\":[\"aws.ecs\"],\"detail-type\":[\"ECS Task State Change\"],\"detail\":{\"clusterArn\":[\"arn:aws:ecs:$R:$ACC:cluster/memme-v2\"],\"lastStatus\":[\"STOPPED\"]}}"
aws events put-rule --name memme-v2-ecs-task-stopped --event-pattern "$PATTERN" \
  --description "memme-v2 ECS task stopped -> SNS memme-v2-alerts" --tags $TAG --query RuleArn --output text
cat > targets.json <<JSON
[{"Id":"sns","Arn":"$TOPIC_ARN","InputTransformer":{
 "InputPathsMap":{"group":"$.detail.group","code":"$.detail.stopCode","reason":"$.detail.stoppedReason","at":"$.detail.stoppedAt"},
 "InputTemplate":"\"[memme-v2] ECS 태스크 중지 | 서비스 <group> | 코드 <code> | 사유 <reason> | 시각(UTC) <at> | 배포 중 교체면 사유에 deployment가 포함됩니다.\""}}]
JSON
aws events put-targets --rule memme-v2-ecs-task-stopped --targets file://targets.json --query FailedEntryCount --output text
echo "A-email done"
