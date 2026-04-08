# DocUnlock Deployment to a Server

<img src="static/img/logo.png" alt="DocUnlock Logo" width="200">

This document contains instructions for deploying DocUnlock to a server.

## Initial Setup

1. Clone the repository:
   ```bash
   cd /home/ubuntu
   git clone https://github.com/subhamsarangi/DocUnlock.git
   cd DocUnlock
   ```

2. Set up virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Set up environment variables (create .env file if needed):
   ```bash
   # Add your ADMIN_PASSPHRASE here
   echo "ADMIN_PASSPHRASE=your_secret_passphrase" > .env
   ```

## Production Run

You may check if the server works or not using

```bash
uvicorn main:app \
  --host 0.0.0.0 \
  --port 8008 \
  --workers 1 \
  --limit-concurrency 20 \
  --backlog 32 \
  --timeout-keep-alive 10
```

**Accessibility**: The app will be accessible at `http://your-server-ip:8008`

## Run as a systemd service

Create `/etc/systemd/system/docunlock.service`:

```ini
[Unit]
Description=DocUnlock FastAPI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/DocUnlock
ExecStart=/home/ubuntu/DocUnlock/venv/bin/uvicorn main:app \
  --host 0.0.0.0 --port 8008 --workers 1 \
  --limit-concurrency 20 --backlog 32
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now docunlock
sudo systemctl start docunlock
sudo systemctl status docunlock

```

## Network Setup

Open port 8008, 80 and 443 in the security list of yout server:

1. Console → Networking → Virtual Cloud Networks → your VCN → Security Lists
2. Add Ingress Rule: Protocol TCP, Destination Port 8008
3. Restrict source CIDR to a particular's IP range, or leave open (0.0.0.0/0) and rely solely on the bearer token.

DO the same for 80 and 443.

Also open the port in the instance firewall:

```bash
sudo iptables -I INPUT -p tcp --dport 8008 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

**Accessibility**: The app will be accessible at `http://your-server-ip:8008`


## Updating Code

On the server, pull changes and restart the service:
   ```bash
   cd /home/ubuntu/DocUnlock
   git pull origin main
   sudo systemctl restart docunlock
   ```

## Debugging

- Check service status:
  ```bash
  sudo systemctl status docunlock
  ```

- View logs:
  ```bash
  sudo journalctl -u docunlock -f
  ```

- Check if port 8008 is listening:
  ```bash
  sudo netstat -tlnp | grep :8008
  ```

- Test the app (on server):
  ```bash
  curl http://localhost:8008
  ```

- Test the app (from outside):
  ```bash
  curl http://your-server-ip:8008  # or http://yourdomain.com
  ```

- If issues, check Python logs in the service output.

## Notes

- Queue max: 6 jobs. When full, uploads return HTTP 503.
- Files auto-deleted after 15 minutes.
- PDF authenticity checked by file header (first 4 bytes = `%PDF`), not extension.
- Max file size: 50 MB.

## Nginx Reverse Proxy Setup and Certbot


### 1. Install Nginx + Certbot

```bash
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx -y
```

---

### 2. Allow HTTP/HTTPS in firewall (if needed)

```bash
sudo ufw allow 'Nginx Full'
```

---

### 3. Create Nginx config

```bash
sudo nano /etc/nginx/sites-available/docunlock
```

Paste:

```nginx
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

### 4. Enable config

```bash
sudo ln -s /etc/nginx/sites-available/docunlock /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

###  Test

Open your site using the domain or the ip. no port needed.

If this works → proceed.

---

###  5. IMPORTANT: You need a DOMAIN (not IP)

👉 **Let’s Encrypt does NOT issue SSL certs for raw IPs**

You must have something like:

```
docunlock.yourdomain.com
```

---

### 6. Point domain to your server

In your domain provider:

* Add **A record**:

```
docunlock → your ip address
```

Wait 2–5 mins.

---

### 7. Run Certbot

```bash
sudo certbot --nginx -d docunlock.yourdomain.com
```

Follow prompts.

---

### 8. Done 🎉

Now open:

```
https://docunlock.yourdomain.com
```

---
