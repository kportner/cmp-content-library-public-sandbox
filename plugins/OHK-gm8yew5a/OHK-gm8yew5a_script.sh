#!/usr/bin/env bash
set -e

mysqlRootPass="{{ server.database_root_password }}"

echo "============================================"
echo " Installing MySQL on Oracle Linux 8 / RHEL 8"
echo "============================================"

echo " -> Stopping existing MySQL service"

systemctl stop mysqld 2>/dev/null || true

echo " -> Removing previous MySQL server installation"

dnf remove -y mysql-server mysql-community-server || true

rm -rf /var/lib/mysql
rm -f /var/log/mysqld.log
rm -f /etc/my.cnf

echo " -> Installing MySQL Community EL8 repository"

dnf install -y \
    https://repo.mysql.com/mysql80-community-release-el8.rpm

echo " -> Importing MySQL GPG key"

rpm --import https://repo.mysql.com/RPM-GPG-KEY-mysql-2022

echo " -> Disabling EL8 built-in MySQL module"

dnf -y module disable mysql || true

echo " -> Installing MySQL Community Server"

dnf install -y mysql-community-server

echo " -> Enabling MySQL service"

systemctl enable mysqld

echo " -> Starting MySQL server"

systemctl start mysqld

echo " -> Checking MySQL service"

if ! systemctl is-active --quiet mysqld; then
    echo "ERROR: MySQL failed to start."
    systemctl --no-pager status mysqld || true
    exit 1
fi

echo " -> Extracting temporary root password"

tempRootDBPass="$(
    grep 'temporary password' /var/log/mysqld.log |
    tail -n 1 |
    awk '{print $NF}'
)"

if [ -z "${tempRootDBPass}" ]; then
    echo "ERROR: Unable to retrieve temporary root password."
    exit 1
fi

echo " -> Setting root password"

MYSQL_PWD="${tempRootDBPass}" \
mysql -u root --connect-expired-password \
    -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '${mysqlRootPass}';"

echo " -> Securing MySQL installation"

MYSQL_PWD="${mysqlRootPass}" mysql -u root <<EOSQL

DELETE FROM mysql.user
WHERE User='';

DROP DATABASE IF EXISTS test;

DELETE FROM mysql.db
WHERE Db='test'
   OR Db='test\\_%';

CREATE USER IF NOT EXISTS 'root'@'%'
IDENTIFIED WITH caching_sha2_password BY '${mysqlRootPass}';

GRANT ALL PRIVILEGES ON *.*
TO 'root'@'%'
WITH GRANT OPTION;

FLUSH PRIVILEGES;

EOSQL

echo " -> Restarting MySQL"

systemctl restart mysqld

echo " -> Verifying MySQL"

if systemctl is-active --quiet mysqld; then
    echo "MySQL service is running successfully."
else
    echo "ERROR: MySQL service failed to restart."
    systemctl --no-pager status mysqld || true
    exit 1
fi

mysql --version

echo "============================================"
echo " MySQL server installation completed."
echo "============================================"