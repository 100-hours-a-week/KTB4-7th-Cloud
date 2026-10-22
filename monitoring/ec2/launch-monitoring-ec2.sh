#!/usr/bin/env bash
# 2단계: 모니터링 SG(인바운드 없음) + EC2(t3.small) 생성 + 상태 검사 알람. CloudShell에서 user-data.sh와 같은 폴더에서 실행.
# 선행 조건: IAM 역할/인스턴스 프로파일 memme-v2-monitoring-role (사용자 직접 생성)
set -euo pipefail
export AWS_PAGER=""
SUBNET=subnet-023daf75ba6f1dfe5          # memme-public-subnet-a (10.0.1.0/24)
NAME=memme-v2-monitoring
PROFILE=memme-v2-monitoring-role
TOPIC=arn:aws:sns:ap-northeast-2:613538400341:memme-v2-alerts

aws iam get-instance-profile --instance-profile-name $PROFILE --query 'InstanceProfile.Roles[0].RoleName' --output text

EXIST=$(aws ec2 describe-instances --filters Name=tag:Name,Values=$NAME Name=instance-state-name,Values=pending,running,stopped \
  --query 'Reservations[].Instances[].InstanceId' --output text)
if [ -n "$EXIST" ]; then echo "already exists: $EXIST"; exit 1; fi

VPC=$(aws ec2 describe-subnets --subnet-ids $SUBNET --query 'Subnets[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=$NAME-sg Name=vpc-id,Values=$VPC --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name $NAME-sg --vpc-id $VPC \
    --description "memme-v2 monitoring server. No inbound; agent rules added later" \
    --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$NAME-sg},{Key=Project,Value=memme-v2}]" \
    --query GroupId --output text)
fi
echo "sg $SG"

AMI=$(aws ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id --query Parameter.Value --output text)
echo "ami $AMI"

IID=$(aws ec2 run-instances --image-id $AMI --instance-type t3.small --subnet-id $SUBNET \
  --security-group-ids $SG --associate-public-ip-address \
  --iam-instance-profile Name=$PROFILE \
  --metadata-options HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --user-data file://user-data.sh \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=Project,Value=memme-v2}]" \
                       "ResourceType=volume,Tags=[{Key=Name,Value=$NAME-root},{Key=Project,Value=memme-v2}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "instance $IID"
aws ec2 wait instance-running --instance-ids $IID
aws ec2 describe-instances --instance-ids $IID --query 'Reservations[0].Instances[0].[InstanceId,PrivateIpAddress,PublicIpAddress,State.Name]' --output text

echo "상태 검사 통과 대기(최대 10분, 시작 직후 오경보 방지)"
aws ec2 wait instance-status-ok --instance-ids $IID
aws cloudwatch put-metric-alarm --alarm-name memme-v2-ec2-monitoring-status \
  --alarm-description "모니터링 서버(Grafana·Prometheus·Loki) EC2 상태 검사 실패 (2분 연속, 데이터 없음도 실패)" \
  --namespace AWS/EC2 --metric-name StatusCheckFailed --dimensions Name=InstanceId,Value=$IID \
  --statistic Maximum --period 60 --evaluation-periods 2 --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data breaching --alarm-actions $TOPIC --ok-actions $TOPIC --tags Key=Project,Value=memme-v2
echo "alarm ok. user-data 설치는 3~5분 걸립니다."
