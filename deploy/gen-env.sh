#!/bin/bash
set -euo pipefail

: "${PUBLIC_ORIGIN:?PUBLIC_ORIGIN is required}"
: "${WEB_PORT:?WEB_PORT is required}"
: "${NETWORK_SUBNET:?NETWORK_SUBNET is required}"
: "${WEB_CONTAINER_IP:?WEB_CONTAINER_IP is required}"

root="$(cd "$(dirname "$0")/.." && pwd)"
target="$root/deploy/.env"
if [ -e "$target" ]; then
  echo "$target already exists" >&2
  exit 1
fi

secret() { openssl rand -hex 24; }
pg_password="$(secret)"
app_user="askmiao_app"
app_password="$(secret)"
fernet_key="$(openssl rand 32 | base64 | tr '+/' '-_' | tr -d '\n')"
cookie_secure=false
case "$PUBLIC_ORIGIN" in
  https://*) cookie_secure=true ;;
esac

umask 077
{
  cat "$root/backend/.env.example"
  cat <<OVERRIDES

HOST=0.0.0.0
ENVIRONMENT=production
COOKIE_SECURE=$cookie_secure
TOOL_SECRETS_KEY=$fernet_key
POSTGRES_PASSWORD=$pg_password
POSTGRES_APP_USER=$app_user
POSTGRES_APP_PASSWORD=$app_password
DATABASE_URL=postgresql+psycopg2://$app_user:$app_password@postgres:5432/chatbot
ALLOWED_ORIGINS=$PUBLIC_ORIGIN
FORWARDED_ALLOW_IPS=$WEB_CONTAINER_IP
WEB_PORT=$WEB_PORT
WEB_CONTAINER_IP=$WEB_CONTAINER_IP
NETWORK_SUBNET=$NETWORK_SUBNET
OVERRIDES
} > "$target"
echo "wrote $target"
