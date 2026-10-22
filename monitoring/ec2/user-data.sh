#!/bin/bash
# memme-v2 모니터링 서버 부팅 스크립트 (Ubuntu 24.04). 설정 파일은 이후 monitoring/server/를 /opt/monitoring에 복사해 적용
set -euxo pipefail
if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile; chmod 600 /swapfile; mkswap /swapfile; swapon /swapfile; echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
mkdir -p /opt/monitoring && chmod 755 /opt/monitoring
