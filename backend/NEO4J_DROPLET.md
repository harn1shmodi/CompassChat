⏺ Neo4j on DigitalOcean Droplet Setup

Step 1: Create Droplet

# Create Ubuntu 22.04 droplet (minimum 2GB RAM recommended)
# Choose your preferred region
# Add SSH key for secure access

Step 2: Initial Server Setup

# SSH into your droplet
ssh root@your_droplet_ip

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Create neo4j user and directories
useradd -m neo4j
mkdir -p /home/neo4j/{data,logs,import,plugins}
chown -R neo4j:neo4j /home/neo4j

⏺ Update Todos
  ⎿  ☒ Create DigitalOcean Droplet setup guide            
     ☐ Provide Docker Neo4j configuration with persistence
     ☐ Configure networking and security
     ☐ Update environment variables for production

⏺ Step 3: Create Docker Compose for Neo4j

  # Create docker-compose.yml
cat > /home/neo4j/docker-compose.yml << 'EOF'
version: '3.8'

services:
  neo4j:
    image: neo4j:5.15-community
    container_name: neo4j-production
    restart: unless-stopped
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/your_secure_password_here
      - NEO4J_PLUGINS=["apoc"]
      - server.default_listen_address=0.0.0.0
      - server.bolt.listen_address=0.0.0.0:7687
      - server.http.listen_address=0.0.0.0:7474
      - server.memory.heap.initial_size=512M
      - server.memory.heap.max_size=1G
      - server.memory.pagecache.size=512M
    volumes:
      - ./data:/data
      - ./logs:/logs
      - ./import:/var/lib/neo4j/import
      - ./plugins:/plugins
    networks:
      - neo4j-network

networks:
  neo4j-network:
    driver: bridge
EOF
cat > /home/neo4j/docker-compose.yml << 'EOF'
version: '3.8'

services:
  neo4j:
    image: neo4j:5.15-community
    container_name: neo4j-production
    restart: unless-stopped
    ports:
    - "7474:7474"
    - "7687:7687"
    environment:
    - NEO4J_AUTH=neo4j/your_secure_password_here
    - NEO4J_PLUGINS=["apoc"]
    - NEO4J_dbms_default__listen__address=0.0.0.0
    - NEO4J_dbms_connector_bolt_listen__address=0.0.0.0:7687
    - NEO4J_dbms_connector_http_listen__address=0.0.0.0:7474
    - NEO4J_dbms_memory_heap_initial__size=1G
    - NEO4J_dbms_memory_heap_max__size=2G
    - NEO4J_dbms_memory_pagecache_size=1G
    volumes:
      - ./data:/data
      - ./logs:/logs
      - ./import:/var/lib/neo4j/import
      - ./plugins:/plugins
    networks:
      - neo4j-network

networks:
  neo4j-network:
    driver: bridge
EOF
  # Set ownership
  chown neo4j:neo4j /home/neo4j/docker-compose.yml

  Step 4: Start Neo4j

  cd /home/neo4j
  docker compose up -d

  # Check status
  docker compose ps
  docker compose logs neo4j

⏺ Update Todos
  ⎿  ☒ Create DigitalOcean Droplet setup guide            
     ☒ Provide Docker Neo4j configuration with persistence
     ☐ Configure networking and security
     ☐ Update environment variables for production

⏺ Step 5: Configure Firewall & Security

  # Install and configure UFW firewall
  ufw allow ssh
  ufw allow 7474/tcp  # Neo4j HTTP
  ufw allow 7687/tcp  # Neo4j Bolt
  ufw --force enable

  # Optional: Restrict access to specific IPs
  # ufw allow from YOUR_APP_PLATFORM_IP to any port 7687
  # ufw allow from YOUR_IP to any port 7474

  Step 6: Test Connection

  # Test from droplet
  curl http://localhost:7474

  # Test from your app (replace with droplet IP)
  curl http://your_droplet_ip:7474

⏺ Update Todos
  ⎿  ☒ Create DigitalOcean Droplet setup guide            
     ☒ Provide Docker Neo4j configuration with persistence
     ☒ Configure networking and security
     ☐ Update environment variables for production

⏺ Step 7: Update Your App Environment Variables

  For App Platform, set these environment variables:
  NEO4J_URI=bolt://your_droplet_ip:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=your_secure_password_here
  NEO4J_DATABASE=neo4j

  For local development, update your .env:
  NEO4J_URI=bolt://your_droplet_ip:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=your_secure_password_here

  Step 8: Persistence & Backup Setup

  # Create backup script
  cat > /home/neo4j/backup.sh << 'EOF'
  #!/bin/bash
  DATE=$(date +%Y%m%d_%H%M%S)
  docker compose exec neo4j neo4j-admin database dump --to-path=/var/lib/neo4j/import neo4j
  cp /home/neo4j/import/neo4j.dump /home/neo4j/backups/neo4j_backup_$DATE.dump
  find /home/neo4j/backups -name "*.dump" -mtime +7 -delete
  EOF

  chmod +x /home/neo4j/backup.sh
  mkdir -p /home/neo4j/backups

  # Add to crontab for daily backups
  echo "0 2 * * * /home/neo4j/backup.sh" | crontab -

  Data Persistence: Your Neo4j data is stored in /home/neo4j/data with Docker volumes, ensuring persistence across container restarts.