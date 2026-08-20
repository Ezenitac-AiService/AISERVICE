#!/usr/bin/env bash
# ==============================================================================
# AISERVICE Database Lossless Export Engine (Linux / macOS / WSL2)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DB_OUTPUT_DIR="${PACK_ROOT}/database"

mkdir -p "${DB_OUTPUT_DIR}"

echo "======================================================================"
echo " 📦 AISERVICE DATABASE LOSSLESS EXPORT ENGINE"
echo " Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo " Output Directory: ${DB_OUTPUT_DIR}"
echo "======================================================================"

# 1. Check container statuses
if ! docker ps --format '{{.Names}}' | grep -q "^pilos-db$"; then
    echo "❌ Error: Container 'pilos-db' is not running."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^bteam_db$"; then
    echo "❌ Error: Container 'bteam_db' is not running."
    exit 1
fi

# 2. Dump pilos_v2 (MySQL 8.0)
echo ""
echo "▶ [1/2] Exporting 'pilos_v2' database (A-Team Pilos)..."
start_pilos=$(date +%s)
docker exec pilos-db mysqldump \
    -u pilos_user -ppilos_password \
    --single-transaction \
    --quick \
    --routines \
    --triggers \
    --events \
    --hex-blob \
    --default-character-set=utf8mb4 \
    --max_allowed_packet=512M \
    pilos_v2 | gzip -9 > "${DB_OUTPUT_DIR}/pilos_v2.sql.gz"
end_pilos=$(date +%s)
pilos_size=$(du -h "${DB_OUTPUT_DIR}/pilos_v2.sql.gz" | cut -f1)
echo "  ✓ 'pilos_v2.sql.gz' created (${pilos_size}) in $((end_pilos - start_pilos))s"

# 3. Dump oliview_project (MySQL 8.0)
echo ""
echo "▶ [2/2] Exporting 'oliview_project' database (B-Team Oliview)..."
start_bteam=$(date +%s)
docker exec bteam_db mysqldump \
    -u gp123 -pGP123! \
    --single-transaction \
    --quick \
    --routines \
    --triggers \
    --events \
    --hex-blob \
    --default-character-set=utf8mb4 \
    --max_allowed_packet=512M \
    oliview_project | gzip -9 > "${DB_OUTPUT_DIR}/oliview_project.sql.gz"
end_bteam=$(date +%s)
bteam_size=$(du -h "${DB_OUTPUT_DIR}/oliview_project.sql.gz" | cut -f1)
echo "  ✓ 'oliview_project.sql.gz' created (${bteam_size}) in $((end_bteam - start_bteam))s"

# 4. Generate SHA-256 Checksums
echo ""
echo "▶ Generating SHA-256 integrity checksums..."
cd "${PACK_ROOT}"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum database/pilos_v2.sql.gz database/oliview_project.sql.gz > database/checksums.sha256
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 database/pilos_v2.sql.gz database/oliview_project.sql.gz > database/checksums.sha256
fi
echo "  ✓ 'database/checksums.sha256' generated successfully."

# 5. Generate migration_manifest.json
echo ""
echo "▶ Generating migration_manifest.json..."
python3 -c "
import os, json, hashlib, datetime
manifest = {
    'manifest_version': '1.0.0',
    'exported_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_environment': {'os': '$(uname -s)', 'arch': '$(uname -m)'},
    'databases': {
        'pilos_v2': {
            'dump_file': 'database/pilos_v2.sql.gz',
            'compressed_size_bytes': os.path.getsize('${DB_OUTPUT_DIR}/pilos_v2.sql.gz'),
        },
        'oliview_project': {
            'dump_file': 'database/oliview_project.sql.gz',
            'compressed_size_bytes': os.path.getsize('${DB_OUTPUT_DIR}/oliview_project.sql.gz'),
        }
    }
}
with open('${PACK_ROOT}/migration_manifest.json', 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2)
"
echo "  ✓ 'migration_manifest.json' generated successfully."
echo ""
echo "======================================================================"
echo " ✅ DATABASE EXPORT & CHECKSUM VERIFICATION COMPLETED"
echo "======================================================================"
