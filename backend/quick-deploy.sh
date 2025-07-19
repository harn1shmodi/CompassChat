#!/bin/bash

# CompassChat Quick Deploy Script
# Run this on your LOCAL machine to deploy to Digital Ocean

set -e

echo "🚀 CompassChat Quick Deploy Script"
echo "=================================="

# Check if droplet IP is provided
if [ -z "$1" ]; then
    echo "Usage: ./quick-deploy.sh <droplet_ip>"
    echo "Example: ./quick-deploy.sh 143.198.123.456"
    exit 1
fi

DROPLET_IP=$1
echo "🎯 Deploying to: $DROPLET_IP"

# Check if .env.production exists
if [ ! -f ".env.production" ]; then
    echo "❌ .env.production file not found!"
    echo "Please edit .env.production with your actual values first."
    exit 1
fi

# Check if OpenAI API key is set
if grep -q "sk-your-openai-api-key-here" .env.production; then
    echo "❌ Please update your OpenAI API key in .env.production"
    echo "Edit the file and replace 'sk-your-openai-api-key-here' with your actual key"
    exit 1
fi

echo "📦 Step 1: Running deployment script on droplet..."
ssh root@$DROPLET_IP 'bash -s' < deploy.sh

echo "📁 Step 2: Uploading application files..."
# Upload entire backend directory
scp -r . root@$DROPLET_IP:/opt/compasschat/

echo "⚙️ Step 3: Transferring environment configuration..."
scp .env.production root@$DROPLET_IP:/opt/compasschat/.env

echo "🔧 Step 4: Setting up SSL certificate..."
read -p "Enter your domain (e.g., compass.yourdomain.com): " DOMAIN
ssh root@$DROPLET_IP << EOF
# Install certbot
apt-get install -y certbot python3-certbot-nginx

# Stop nginx to allow certbot to bind to port 80
systemctl stop nginx

# Get certificate
certbot certonly --standalone -d $DOMAIN

# Copy certificates to docker volume
mkdir -p /opt/compasschat/ssl
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /opt/compasschat/ssl/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /opt/compasschat/ssl/

# Update nginx config with actual domain
sed -i "s/compass.yourdomain.com/$DOMAIN/g" /opt/compasschat/nginx.conf

# Update environment file with actual domain
sed -i "s/compass.yourdomain.com/$DOMAIN/g" /opt/compasschat/.env
EOF

echo "🚀 Step 5: Starting application..."
ssh root@$DROPLET_IP << 'EOF'
cd /opt/compasschat
systemctl start compasschat
sleep 10
systemctl status compasschat
EOF

echo "🔍 Step 6: Testing deployment..."
sleep 5
if curl -f -s https://$DOMAIN/health > /dev/null; then
    echo "✅ Deployment successful!"
    echo "🌐 Your app is live at: https://$DOMAIN"
else
    echo "⚠️  Deployment may have issues. Check logs:"
    echo "   ssh root@$DROPLET_IP"
    echo "   cd /opt/compasschat"
    echo "   ./monitor.sh"
fi

echo ""
echo "🎉 Deployment Complete!"
echo "=================================="
echo "🌐 URL: https://$DOMAIN"
echo "📊 Monitor: ssh root@$DROPLET_IP '/opt/compasschat/monitor.sh'"
echo "📋 Logs: ssh root@$DROPLET_IP 'cd /opt/compasschat && docker-compose -f docker-compose.prod.yml logs -f'"
echo ""
echo "🔧 Management Commands:"
echo "  Restart: ssh root@$DROPLET_IP 'systemctl restart compasschat'"
echo "  Status:  ssh root@$DROPLET_IP 'systemctl status compasschat'"
echo "  Backup:  ssh root@$DROPLET_IP '/opt/compasschat/backup.sh'"