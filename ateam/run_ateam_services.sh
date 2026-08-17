#!/usr/bin/env bash
# run_ateam_services.sh: A-Team Container Services Manager
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMMAND="${1:-start}"

case "$COMMAND" in
    start)
        echo "=== [1/3] Initializing network ==="
        bash "$SCRIPT_DIR/scripts/init_network.sh"
        echo "=== [2/3] Starting A-Team containers (Web: 8080, DB: 3307) ==="
        docker compose up -d --build
        echo "=== [SUCCESS] A-Team services started! ==="
        echo "Web Dashboard: http://localhost:8080"
        echo "Database Port: localhost:3307"
        ;;
    stop)
        echo "Stopping A-Team containers..."
        docker compose down
        echo "=== [SUCCESS] A-Team services stopped. ==="
        ;;
    restart)
        echo "Restarting A-Team containers..."
        docker compose restart
        ;;
    logs)
        docker compose logs -f
        ;;
    status)
        docker compose ps
        ;;
    init-db)
        echo "Starting DB dump restoration (pilos_v2.sql)..."
        bash "$SCRIPT_DIR/scripts/import_db_dump.sh"
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|logs|status|init-db]"
        exit 1
        ;;
esac
