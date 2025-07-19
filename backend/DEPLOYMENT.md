# CompassChat Digital Ocean Deployment Guide

## 🚀 Quick Deployment Steps

### Step 1: Create Digital Ocean Droplet
1. Go to [Digital Ocean](https://digitalocean.com) and create a new droplet
2. **Choose Image**: Ubuntu 22.04 LTS
3. **Choose Size**: Basic plan, 2 GB RAM, 2 vCPUs, 50 GB SSD ($24/month)
4. **Choose Region**: Closest to your users
5. **Add SSH Key**: Upload your SSH public key
6. **Create Droplet**

### Step 2: Point Your Subdomain to Digital Ocean
1. In your DNS provider (where your main domain is hosted):
   - Add A record: `compass.yourdomain.com` → `your_droplet_ip`
   - TTL: 300 seconds (5 minutes)
2. Wait for DNS propagation (~5-10 minutes)

### Step 3: Deploy to Droplet
```bash
# SSH into your droplet
ssh root@your_droplet_ip

# Download and run deployment script
curl -fsSL https://raw.githubusercontent.com/yourusername/compasschat/main/backend/deploy.sh -o deploy.sh
chmod +x deploy.sh
./deploy.sh
```

### Step 4: Upload Your Application
```bash
# On your local machine, upload your app
scp -r backend/ root@your_droplet_ip:/opt/compasschat/

# Or use git (recommended)
ssh root@your_droplet_ip
cd /opt/compasschat
git clone https://github.com/yourusername/compasschat.git .
```

### Step 5: Configure Environment

#### Option A: Transfer your pre-configured .env file
```bash
# On your local machine, edit the production env file
nano backend/.env.production
# Add your OpenAI API key and update domain

# Transfer to droplet
scp backend/.env.production root@your_droplet_ip:/opt/compasschat/.env
```

#### Option B: Edit directly on server
```bash
# Edit environment file on server
nano /opt/compasschat/.env

# Add your actual values:
NEO4J_PASSWORD=your_secure_password_123
OPENAI_API_KEY=sk-your-openai-api-key
REDIS_PASSWORD=your_redis_password_123
CORS_ORIGINS=["https://compass.yourdomain.com"]
```

### Step 6: Get SSL Certificate (Free with Let's Encrypt)
```bash
# Install certbot
apt-get install -y certbot python3-certbot-nginx

# Get certificate
certbot --nginx -d compass.yourdomain.com

# Copy certificates to docker volume
cp /etc/letsencrypt/live/compass.yourdomain.com/fullchain.pem /opt/compasschat/ssl/
cp /etc/letsencrypt/live/compass.yourdomain.com/privkey.pem /opt/compasschat/ssl/
```

### Step 7: Start Application
```bash
cd /opt/compasschat
systemctl start compasschat
systemctl status compasschat
```

## 🔧 Management Commands

### Check Status
```bash
/opt/compasschat/monitor.sh
```

### View Logs
```bash
cd /opt/compasschat
docker-compose -f docker-compose.prod.yml logs -f app
```

### Restart Application
```bash
systemctl restart compasschat
```

### Create Backup
```bash
/opt/compasschat/backup.sh
```

### Update Application
```bash
cd /opt/compasschat
git pull origin main
docker-compose -f docker-compose.prod.yml build
systemctl restart compasschat
```

## 📊 Resource Usage for 5 Users

### Expected Load:
- **Memory**: ~1.5GB (Neo4j: 1GB, App: 300MB, Redis: 200MB)
- **CPU**: ~20% average (spikes to 80% during repository analysis)
- **Storage**: ~5GB database + 1GB temp files per concurrent analysis
- **Network**: ~50MB/analysis (downloading repos)

### Concurrency Handling:
- **Current**: No explicit limits, FastAPI handles requests naturally
- **Repository Analysis**: 1-2 concurrent analyses should work fine
- **Chat Requests**: Can handle 10+ concurrent users easily
- **Database**: Neo4j can handle 50+ concurrent queries

## 🌐 Subdomain Setup with Fly.io

### DNS Configuration:
```
yourdomain.com        A    fly.io.ip.address      (your main site)
compass.yourdomain.com A    digitalocean.ip.address (CompassChat)
```

### No Conflicts:
- Different subdomains route to different servers
- No CORS issues since they're different origins
- SSL certificates are separate

## 📈 Cost Breakdown

### Monthly Costs:
- **Droplet**: $24/month (2GB RAM, 2 vCPUs)
- **Block Storage**: $5/month (50GB additional storage)
- **Bandwidth**: Free (1TB included)
- **Backups**: $5/month (optional automatic backups)

**Total**: ~$29-34/month

### Alternative Cheaper Setup:
- **Droplet**: $12/month (1GB RAM, 1 vCPU) - might be tight for Neo4j
- **Use SQLite only**: Skip Neo4j for even cheaper option

## 🔒 Security Notes

### What's Included:
- Non-root Docker user
- Firewall configuration (ufw)
- SSL/TLS encryption
- Rate limiting via nginx
- Basic security headers

### What's Not Included (but you said you don't care):
- Password hashing improvements
- Input validation
- Authentication rate limiting
- Session security

## 🚨 Known Issues & Limitations

### Repository Storage:
✅ **Resolved**: Temp files are automatically cleaned up after analysis

### Concurrency:
- No explicit queue system for repository analysis
- Multiple large repositories could cause memory issues
- Recommendation: Analyze repos one at a time for now

### Database:
- Using SQLite for user data (fine for 5 users)
- Neo4j for graph data (requires 1GB+ RAM)
- No database connection pooling

## 🎯 Production Readiness Score

| Component | Status | Notes |
|-----------|---------|--------|
| **Files** | ✅ Ready | All deployment files created |
| **Storage** | ✅ Ready | Temp cleanup implemented |
| **Scaling** | ⚠️ Basic | Good for 5 users, manual scaling needed |
| **Security** | ❌ Minimal | Basic SSL, no auth security |
| **Monitoring** | ⚠️ Basic | Health checks, basic monitoring |
| **Backups** | ✅ Ready | Automated backup script |

## 🚀 Quick Start Commands

```bash
# Complete deployment in one go
curl -fsSL https://raw.githubusercontent.com/yourusername/compasschat/main/backend/deploy.sh | bash

# Upload your app
scp -r backend/ root@your_droplet_ip:/opt/compasschat/

# Configure and start
ssh root@your_droplet_ip
cd /opt/compasschat
nano .env  # Add your credentials
systemctl start compasschat
```

Your app will be live at `https://compass.yourdomain.com` 🎉