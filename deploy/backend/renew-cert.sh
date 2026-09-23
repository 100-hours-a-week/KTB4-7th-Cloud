#!/usr/bin/env bash
set -Eeuo pipefail

docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /opt/memme/acme-challenge:/var/www/acme \
  certbot/certbot:v5.8.0 renew --quiet

docker exec memme-backend-nginx-1 nginx -s reload
