#!/usr/bin/env bash
# init_network.sh: aiservice-network Docker network initialization script
set -e

NETWORK_NAME="aiservice-network"

echo "Checking Docker network: ${NETWORK_NAME}..."

if docker network ls --filter name=^${NETWORK_NAME}$ --format "{{.Name}}" | grep -w "${NETWORK_NAME}" > /dev/null 2>&1; then
    echo "Docker network '${NETWORK_NAME}' already exists."
else
    echo "Creating Docker network '${NETWORK_NAME}'..."
    docker network create "${NETWORK_NAME}"
    echo "Successfully created Docker network '${NETWORK_NAME}'."
fi
