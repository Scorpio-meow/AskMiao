#!/bin/bash
# 建立後端連線用的帳號（非超級使用者），並把 init.sql 建立的資料表交給它擁有。
# 後端啟動時會建立與修改自己的資料表（create_all、upgrade_schema），只需要 public schema 的 CREATE 權限，
# 不需要超級使用者：即使出現 SQL 注入，也無法讀取伺服器檔案或執行系統指令。
# 由 docker-compose.yml 掛載到 /docker-entrypoint-initdb.d/，在 init.sql 之後執行；
# 既有資料卷升級時，先以新的設定重建容器（docker compose up -d，讓容器取得 POSTGRES_APP_* 與本腳本的掛載），
# 再以 docker compose exec postgres bash /docker-entrypoint-initdb.d/20-app-role.sh 手動執行一次。
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$POSTGRES_APP_USER" -v app_password="$POSTGRES_APP_PASSWORD" -v db_name="$POSTGRES_DB" <<'EOSQL'
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec
ALTER ROLE :"app_user" WITH PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
SELECT format('ALTER TABLE %I.%I OWNER TO %I', schemaname, tablename, :'app_user')
FROM pg_tables
WHERE schemaname = 'public'
\gexec
EOSQL
