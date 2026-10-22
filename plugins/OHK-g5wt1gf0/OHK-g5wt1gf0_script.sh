#!/usr/bin/env bash

set -e

# Stop PostgreSQL
echo "Stopping PostgreSQL..."

systemctl stop postgresql

echo "PostgreSQL stopped successfully."

echo "DONE!"