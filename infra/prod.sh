#!/usr/bin/env bash
# Mọi lệnh với stack production đi qua đây: ./infra/prod.sh up -d --build | ps | logs -f api | exec api ...
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose -f docker-compose.prod.yml --env-file .env.prod "$@"
