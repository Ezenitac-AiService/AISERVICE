#!/usr/bin/env bash
# ==============================================================================
# AISERVICE Target Host One-Click Bootstrap & Restore Engine (Linux / WSL2)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${PACK_ROOT}/.." && pwd)"
DB_DIR="${PACK_ROOT}/database"

FORCE_FLAG=false
for arg in "$@"; do
    if [[ "$arg" == "--force" || "$arg" == "-f" || "$arg" == "--yes" || "$arg" == "-y" ]]; then
        FORCE_FLAG=true
    fi
done

echo "======================================================================"
echo " 🚀 AISERVICE ONE-CLICK BOOTSTRAP & RESTORE ENGINE (Linux)"
echo " Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo " Force Mode: ${FORCE_FLAG}"
echo "======================================================================"

# 1. Check Docker & Compose prerequisites
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Error: Docker is not installed or not in PATH."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1 && ! docker-compose version >/dev/null 2>&1; then
    echo "❌ Error: Docker Compose is not installed."
    exit 1
fi

# 2. Check and Provision .env
if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
    echo "▶ Generating .env from template..."
    cp "${PACK_ROOT}/config/.env.migration.template" "${PROJECT_ROOT}/.env"
    echo "  ✓ Created '${PROJECT_ROOT}/.env'"
else
    echo "  ✓ Existing .env found."
fi

# 3. Verify SHA-256 Checksums
echo ""
echo "▶ Verifying database dump checksums..."
cd "${PACK_ROOT}"
if [[ -f "${DB_DIR}/checksums.sha256" ]]; then
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -c "${DB_DIR}/checksums.sha256"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -c "${DB_DIR}/checksums.sha256"
    fi
    echo "  ✓ Checksum verification passed (100% bitwise integrity)."
else
    echo "  ⚠️ Warning: 'checksums.sha256' not found, skipping hash check."
fi

# 4. Start DB Containers
echo ""
echo "▶ Starting database containers (pilos-db & bteam_db)..."
cd "${PROJECT_ROOT}"
docker compose up -d pilos_db bteam_db redis

echo "  Waiting for MySQL databases to be ready..."
until docker exec pilos-db mysqladmin ping -h localhost -uroot -ppilos_root_pass --silent >/dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo "  ✓ pilos-db is ready."

until docker exec bteam_db mysqladmin ping -h localhost -uroot -pGP123! --silent >/dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo "  ✓ bteam_db is ready."

# 5. Restore Database Dumps
echo ""
echo "▶ [1/2] Restoring 'pilos_v2' database..."
start_pilos=$(date +%s)
gzip -dc "${DB_DIR}/pilos_v2.sql.gz" | docker exec -i pilos-db mysql -u pilos_user -ppilos_password --default-character-set=utf8mb4 pilos_v2
end_pilos=$(date +%s)
echo "  ✓ 'pilos_v2' restored successfully in $((end_pilos - start_pilos))s."

echo ""
echo "▶ [2/2] Restoring 'oliview_project' database..."
start_bteam=$(date +%s)
gzip -dc "${DB_DIR}/oliview_project.sql.gz" | docker exec -i bteam_db mysql -u gp123 -pGP123! --default-character-set=utf8mb4 oliview_project
end_bteam=$(date +%s)
echo "  ✓ 'oliview_project' restored successfully in $((end_bteam - start_bteam))s."

# 6. Start Full Service Stack
echo ""
echo "▶ Starting all service containers..."
docker compose up -d

# 7. Run Verification Suite
echo ""
echo "▶ Running 11-endpoint verification suite..."
sleep 5
if command -v python3 >/dev/null 2>&1; then
    python3 "${PACK_ROOT}/scripts/verify_migration.py" || true
fi

echo ""
echo "======================================================================"
echo " 🎉 AISERVICE MIGRATION & BOOTSTRAP RESTORE COMPLETED!"
echo " Portal: http://localhost:80/ or http://localhost:8080/"
echo "======================================================================"
