#!/bin/bash
# Runs ONCE, automatically, when the postgres container starts with an EMPTY
# postgres_data volume (docker-entrypoint-initdb.d semantics). Creates the three
# WSO2 databases and loads them from the seed dumps — which capture a fully
# configured lab (IS Service Provider + GitHub connection, APIM Key Manager,
# LabAPI published + subscribed). Result: clone → docker compose up → test.
#
# If a seed dump is missing, falls back to the vanilla WSO2 schema for that DB
# (server boots but needs manual console setup, as in the pre-seed era).
set -e

for db in shared_db identity_db apim_db; do
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE $db;"

  seed="/docker-entrypoint-initdb.d/seed/$db.sql"
  if [ -f "$seed" ]; then
    echo ">>> seeding $db from configured-lab dump"
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -f "$seed"
  else
    echo ">>> WARNING: no seed dump for $db — loading vanilla schema (manual WSO2 console setup will be required)"
    case "$db" in
      shared_db)   psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -f /wso2-schemas/shared.sql ;;
      identity_db) psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -f /wso2-schemas/identity_correct.sql
                   psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -f /wso2-schemas/consent.sql ;;
      apim_db)     psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -f /wso2-schemas/apim.sql ;;
    esac
  fi
done

echo ">>> WSO2 databases ready"
