#!/bin/bash
set -e

echo "=========================================================="
echo "   Setting up EventEase on AWS EC2 (Ubuntu)"
echo "=========================================================="

# Update and install dependencies
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv libpq-dev openssl curl

# Create project dir if needed
cd "$(dirname "$0")"

# Setup virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt

# SSL Certs
mkdir -p certs
if [ ! -f certs/cert.pem ]; then
    openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes -subj "/CN=localhost"
fi

# Neon PostgreSQL Database URL
export DATABASE_URL="postgresql://neondb_owner:npg_XItPTRW76reE@ep-icy-king-b5gp9r5w-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
export ADMIN_KEY="secret"

# Initialize & seed DB
python init_db.py

# Create systemd service for 24/7 background operation
USER_NAME=$(whoami)
PROJECT_DIR=$(pwd)

sudo tee /etc/systemd/system/eventease.service > /dev/null <<EOF
[Unit]
Description=EventEase Full Stack with Load Balancer and Rate Limiting
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${PROJECT_DIR}
Environment="DATABASE_URL=${DATABASE_URL}"
Environment="ADMIN_KEY=${ADMIN_KEY}"
Environment="HTTP_PORT=80"
Environment="HTTPS_PORT=443"
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/start_all.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Update start_all.py ports for standard HTTP/HTTPS (ports 80 and 443)
sed -i 's/http_port: int = 8080/http_port: int = 80/g' start_all.py || true
sed -i 's/https_port: int = 8443/https_port: int = 443/g' start_all.py || true
sed -i 's/8080/80/g' load_balancer.py || true
sed -i 's/8443/443/g' load_balancer.py || true

# Reload systemd and start EventEase
sudo systemctl daemon-reload
sudo systemctl enable eventease
sudo systemctl restart eventease

echo "=========================================================="
echo "   EventEase is now running 24/7 on AWS EC2!"
echo "   Status: sudo systemctl status eventease"
echo "=========================================================="
