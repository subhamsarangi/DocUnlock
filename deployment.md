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
  --host 127.0.0.1 --port 8008 --workers 1 \
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

Open port 8000 in the security list:

1. Console → Networking → Virtual Cloud Networks → your VCN → Security Lists
2. Add Ingress Rule: Protocol TCP, Destination Port 8000
3. Restrict source CIDR to a particular's IP range, or leave open (0.0.0.0/0) and rely solely on the bearer token.

Also open the port in the instance firewall:

```bash
sudo iptables -I INPUT -p tcp --dport 8008 -j ACCEPT
sudo netfilter-persistent save
```


**Note**: The systemd service binds to 127.0.0.1 (localhost) for security, so it's only accessible via Nginx reverse proxy or direct localhost access on the server.

## Nginx reverse proxy (recommended)

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    client_max_body_size 55M;

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }
}
```

Use certbot for HTTPS.

**Accessibility**: With Nginx, the site is accessible at `http://yourdomain.com` (or `https://` after certbot).

## Updating Code

When you update the code locally:

1. Commit and push changes to Git:
   ```bash
   git add .
   git commit -m "Update message"
   git push origin main
   ```

2. On the server, pull changes and restart the service:
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