# PostPilot Flask - Deployment Guide

This guide covers various deployment options for the PostPilot Flask application.

## Table of Contents
1. [Local Development](#local-development)
2. [Production Deployment](#production-deployment)
3. [Docker Deployment](#docker-deployment)
4. [Cloud Platforms](#cloud-platforms)
5. [Monitoring & Logging](#monitoring--logging)
6. [Troubleshooting](#troubleshooting)

---

## Local Development

### Quick Start
```bash
# Clone/setup the repository
cd postpilot

# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py

# Access at http://localhost:5000
```

### With Auto-Reload
```bash
# Install additional package
pip install python-dotenv

# Create .env file
cp .env.example .env
# Edit .env with your settings

# Run Flask in development mode
export FLASK_ENV=development
python app.py
```

---

## Production Deployment

### Prerequisites
- Python 3.7+
- Gunicorn (included in requirements.txt)
- Nginx or Apache (optional, for reverse proxy)

### Option 1: Direct Server

#### Using Gunicorn
```bash
# Install dependencies
pip install -r requirements.txt

# Run with Gunicorn (4 workers, port 5000)
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app

# Or use the production script
./run-production.sh 4 5000
```

#### Using Systemd Service
Create `/etc/systemd/system/postpilot.service`:
```ini
[Unit]
Description=PostPilot Flask Application
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/postpilot
Environment="PATH=/var/www/postpilot/venv/bin"
ExecStart=/var/www/postpilot/venv/bin/gunicorn \
    --workers 4 \
    --bind unix:/var/www/postpilot/postpilot.sock \
    --timeout 120 \
    app:app

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable postpilot
sudo systemctl start postpilot
sudo systemctl status postpilot
```

### Option 2: Reverse Proxy with Nginx

#### Nginx Configuration
```nginx
upstream postpilot {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name example.com;

    client_max_body_size 16M;

    location / {
        proxy_pass http://postpilot;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /static/ {
        alias /var/www/postpilot/static/;
        expires 30d;
    }

    location /images/ {
        alias /var/www/postpilot/images/;
        expires 7d;
    }
}
```

#### With HTTPS (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d example.com
```

---

## Docker Deployment

### Build Docker Image
```bash
# Build the image
docker build -t postpilot:latest .

# Run the container
docker run -d \
    --name postpilot \
    -p 5000:5000 \
    -v $(pwd)/posts:/app/posts \
    -v $(pwd)/images:/app/images \
    postpilot:latest
```

### Using Docker Compose
```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f postpilot

# Stop the service
docker-compose down
```

### Docker Hub Deployment
```bash
# Login to Docker Hub
docker login

# Tag image
docker tag postpilot:latest yourusername/postpilot:latest

# Push to Docker Hub
docker push yourusername/postpilot:latest

# Pull and run from another machine
docker run -d -p 5000:5000 yourusername/postpilot:latest
```

---

## Cloud Platforms

### Heroku Deployment

1. Create `Procfile`:
```
web: gunicorn app:app
worker: python -c "import tour, visa, insta; tour.run_tour()"
```

2. Create `runtime.txt`:
```
python-3.11.0
```

3. Deploy:
```bash
heroku create postpilot
git push heroku main
heroku logs --tail
```

### PythonAnywhere Deployment

1. Upload files to PythonAnywhere
2. Create virtual environment
3. Configure web app with WSGI file pointing to `app:app`
4. Set up scheduled tasks for posting

### AWS EC2 Deployment

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3 python3-pip nginx

# Clone repository
git clone <repo-url>
cd postpilot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Create systemd service (see Systemd Service section above)
# Configure Nginx (see Nginx Configuration section above)

# Start services
sudo systemctl start postpilot
sudo systemctl start nginx
```

### Google Cloud Run

```bash
# Build and deploy
gcloud run deploy postpilot \
    --source . \
    --platform managed \
    --memory 512M \
    --port 5000 \
    --allow-unauthenticated
```

### DigitalOcean App Platform

1. Connect GitHub repository
2. Configure build settings:
   - Python 3.11
   - pip install -r requirements.txt
   - Run command: `gunicorn app:app`
3. Deploy

---

## Monitoring & Logging

### Application Logs
```bash
# With systemd
sudo journalctl -u postpilot -f

# With Docker
docker-compose logs -f postpilot

# With Gunicorn
gunicorn --access-logfile access.log --error-logfile error.log app:app
```

### Health Checks
```bash
# Check API status
curl http://localhost:5000/api/status

# Check if posts are loading
curl http://localhost:5000/api/posts/tour

# Monitor uptime with monitoring tools
# Example: Uptime Robot, Pingdom, etc.
```

### Performance Monitoring
- Monitor CPU and memory usage
- Track request response times
- Log Facebook API errors
- Monitor disk space for image uploads

---

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>
```

### Facebook API Errors
1. Verify access token is valid
2. Check token hasn't expired
3. Verify page ID is correct
4. Check rate limits haven't been exceeded

### Image Upload Issues
1. Check directory permissions: `chmod 755 images`
2. Verify disk space: `df -h`
3. Check max upload size in nginx/app config

### Static Files Not Loading
1. Verify static folder exists
2. Check file permissions
3. Verify Flask is serving static files correctly
4. Check Nginx configuration if using reverse proxy

### Database/File Locking
```bash
# Ensure only one process is running
ps aux | grep app.py

# Check file permissions
ls -la posts/
```

---

## Production Checklist

- [ ] Update Facebook API credentials
- [ ] Set `FLASK_DEBUG=0`
- [ ] Set `FLASK_ENV=production`
- [ ] Configure HTTPS/SSL
- [ ] Set up proper logging
- [ ] Configure monitoring/alerting
- [ ] Set up automated backups for posts/images
- [ ] Configure rate limiting
- [ ] Set up CI/CD pipeline
- [ ] Test all endpoints
- [ ] Configure firewall rules
- [ ] Set up email notifications for errors

---

## Backup & Recovery

### Backup Posts and Images
```bash
# Create backup
tar -czf postpilot_backup_$(date +%Y%m%d).tar.gz posts/ images/

# Store securely
cp postpilot_backup_*.tar.gz /backup/location/
```

### Restore from Backup
```bash
tar -xzf postpilot_backup_YYYYMMDD.tar.gz
```

---

## Support & Resources

- Flask Documentation: https://flask.palletsprojects.com/
- Gunicorn Documentation: https://gunicorn.org/
- Docker Documentation: https://docs.docker.com/
- Facebook Graph API: https://developers.facebook.com/docs/graph-api

---

**Last Updated**: February 7, 2026
