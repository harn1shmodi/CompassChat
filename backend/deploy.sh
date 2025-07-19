#!/bin/bash

# CompassChat Digital Ocean Deployment Script
# Run this script on your Digital Ocean droplet

set -e

echo "🚀 Starting CompassChat deployment..."

# Update system
echo "📦 Updating system packages..."
apt-get update && apt-get upgrade -y

# Install Docker and Docker Compose
echo "🐳 Installing Docker..."
apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start Docker service
systemctl start docker
systemctl enable docker

# Add current user to docker group
usermod -aG docker $USER

# Install Docker Compose (standalone)
echo "📦 Installing Docker Compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Create application directory
echo "📁 Creating application directory..."
mkdir -p /opt/compasschat
cd /opt/compasschat

# Create environment file
echo "⚙️ Creating environment file..."
cat > .env << 'EOF'
# Neo4j Configuration
NEO4J_PASSWORD=your_secure_neo4j_password_here

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Redis Configuration
REDIS_PASSWORD=your_secure_redis_password_here

# Application Settings
CORS_ORIGINS=["https://compass.yourdomain.com"]
DEBUG=false
EOF

echo "✅ Environment file created at /opt/compasschat/.env"
echo "⚠️  IMPORTANT: Edit /opt/compasschat/.env with your actual credentials!"

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data ssl

# Create SSL certificate placeholder
echo "🔒 Creating SSL certificate placeholder..."
mkdir -p ssl
echo "# Place your SSL certificates here:" > ssl/README.md
echo "# - fullchain.pem (certificate chain)" >> ssl/README.md
echo "# - privkey.pem (private key)" >> ssl/README.md

# Create systemd service for auto-startup
echo "🔧 Creating systemd service..."
cat > /etc/systemd/system/compasschat.service << 'EOF'
[Unit]
Description=CompassChat Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/compasschat
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable service
systemctl daemon-reload
systemctl enable compasschat.service

# Setup log rotation
echo "📋 Setting up log rotation..."
cat > /etc/logrotate.d/compasschat << 'EOF'
/var/lib/docker/containers/*/*-json.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
}
EOF

# Create backup script
echo "💾 Creating backup script..."
cat > /opt/compasschat/backup.sh << 'EOF'
#!/bin/bash
# CompassChat Backup Script

BACKUP_DIR="/opt/compasschat/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

echo "🗄️ Creating backup: $DATE"

# Backup SQLite database
if [ -f "./compasschat.db" ]; then
    cp ./compasschat.db "$BACKUP_DIR/compasschat_$DATE.db"
    echo "✅ SQLite database backed up"
fi

# Backup Neo4j data
docker-compose -f docker-compose.prod.yml exec -T neo4j neo4j-admin database dump --to-path=/var/lib/neo4j/dumps neo4j
docker cp $(docker-compose -f docker-compose.prod.yml ps -q neo4j):/var/lib/neo4j/dumps/neo4j.dump "$BACKUP_DIR/neo4j_$DATE.dump"
echo "✅ Neo4j database backed up"

# Backup environment file
cp .env "$BACKUP_DIR/env_$DATE"
echo "✅ Environment file backed up"

# Keep only last 7 backups
find $BACKUP_DIR -name "*.db" -type f -mtime +7 -delete
find $BACKUP_DIR -name "*.dump" -type f -mtime +7 -delete
find $BACKUP_DIR -name "env_*" -type f -mtime +7 -delete

echo "✅ Backup completed: $BACKUP_DIR"
EOF

chmod +x /opt/compasschat/backup.sh

# Create monitoring script
echo "📊 Creating monitoring script..."
cat > /opt/compasschat/monitor.sh << 'EOF'
#!/bin/bash
# CompassChat Monitoring Script

echo "🔍 CompassChat System Status"
echo "=========================="

# Check Docker containers
echo "📦 Container Status:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "💾 Disk Usage:"
df -h /

echo ""
echo "🧠 Memory Usage:"
free -h

echo ""
echo "📊 Docker System Usage:"
docker system df

echo ""
echo "🔗 Service Health:"
curl -s http://localhost:8000/health | python3 -m json.tool || echo "❌ Health check failed"

echo ""
echo "📋 Recent Logs (last 10 lines):"
docker-compose -f docker-compose.prod.yml logs --tail=10 app
EOF

chmod +x /opt/compasschat/monitor.sh

# Setup firewall
echo "🔥 Configuring firewall..."
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "✅ Deployment script completed!"
echo ""
echo "📋 Next Steps:"
echo "1. Edit /opt/compasschat/.env with your actual credentials"
echo "2. Upload your application files to /opt/compasschat/"
echo "3. Add your SSL certificates to /opt/compasschat/ssl/"
echo "4. Run: systemctl start compasschat"
echo "5. Check status: systemctl status compasschat"
echo ""
echo "🔧 Useful Commands:"
echo "- Monitor: /opt/compasschat/monitor.sh"
echo "- Backup: /opt/compasschat/backup.sh"
echo "- Logs: docker-compose -f docker-compose.prod.yml logs -f"
echo "- Restart: systemctl restart compasschat"
echo ""
echo "🌐 Your app will be available at: https://compass.yourdomain.com"