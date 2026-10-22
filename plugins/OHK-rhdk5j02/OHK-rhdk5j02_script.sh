#!/usr/bin/env bash

set -e

echo "========================================"
echo " Installing PostgreSQL on OEL 8 / RHEL 8"
echo "========================================"

# Must be run as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root."
    exit 1
fi

echo "Installing PostgreSQL server and contrib packages..."
dnf install -y postgresql-server postgresql-contrib

echo "Checking PostgreSQL database initialization..."

# Initialize only if PostgreSQL has not already been initialized
if [ ! -f /var/lib/pgsql/data/PG_VERSION ]; then
    echo "Initializing PostgreSQL database..."
    postgresql-setup --initdb
else
    echo "PostgreSQL database is already initialized. Skipping initdb."
fi

echo "Enabling PostgreSQL to start automatically on reboot..."
systemctl enable postgresql

echo "Starting PostgreSQL..."
systemctl start postgresql

echo "Checking PostgreSQL service..."
if systemctl is-active --quiet postgresql; then
    echo "PostgreSQL is running successfully."
else
    echo "ERROR: PostgreSQL failed to start."
    systemctl --no-pager status postgresql
    exit 1
fi

echo "Opening incoming TCP port 5432..."

if systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port=5432/tcp
    firewall-cmd --reload
    echo "TCP port 5432 opened successfully."
else
    echo "WARNING: firewalld is not running."
    echo "Skipping firewall configuration for port 5432."
fi

echo "========================================"
echo " PostgreSQL installation completed."
echo "========================================"