# Server setup + Cloudflare Tunnel (human guide)

This README shows a practical baseline for a fresh Ubuntu server: basic hardening, Docker, and exposing services through Cloudflare Tunnel (no router port-forwarding needed). Cloudflare Tunnel lets you publish services without a publicly routable IP by running `cloudflared` on your server and connecting it to Cloudflare. [web:61]

## Assumptions

- OS: Ubuntu Server 22.04/24.04.
- You have SSH access to the server.
- Your domain is added to Cloudflare and DNS is managed there.
- You want to expose a local service like `http://localhost:8080` to `https://app.yourdomain.com`.

## 1) First login + updates

SSH into the server:

```bash
ssh user@SERVER_IP
Update packages:

bash
sudo apt update
sudo apt -y upgrade
2) Firewall (UFW) without locking yourself out
Before enabling UFW, allow SSH, otherwise you can lock yourself out of the server as soon as UFW turns on. [web:52][web:58]

bash
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status verbose
Optional baseline policies (common “secure default”):

bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw status verbose
3) Docker (optional but common)
If your apps will run in containers, install Docker and the Compose plugin. Docker Compose v2 is used as docker compose (no hyphen), and the Compose plugin can be installed via docker-compose-plugin. [web:68]

Simple Ubuntu-packaged install:

bash
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
docker --version
docker compose version
(If you prefer Docker CE from Docker’s repo, follow official instructions for your distro, but the above is fine for many setups.) [web:68]

4) Cloudflare Tunnel (cloudflared)
Cloudflare provides docs for creating a tunnel via the dashboard or as a locally-managed tunnel via CLI, and both routes end up with a tunnel + routing rules (ingress) that point hostnames to local services. [web:47][web:62]

4.1 Create the tunnel in the Cloudflare dashboard
In Cloudflare Zero Trust:

Networks → Connectors → Cloudflare Tunnels → Create a tunnel. [web:47]

Choose Cloudflared, give it a name. [web:47]

Cloudflare will show commands/instructions specific to your tunnel. Follow those for the cleanest setup. [web:47]

4.2 Install cloudflared on the server
Install cloudflared (package name varies by distro; use Cloudflare’s instructions shown in the dashboard if needed). [web:62]

After install, authenticate:

bash
cloudflared tunnel login
This links your machine to your Cloudflare account. [web:62]

4.3 Local tunnel creation (CLI alternative)
If you’re doing a locally-managed tunnel via CLI, Cloudflare’s flow is:

install cloudflared

authenticate

cloudflared tunnel create <name>

create a config.yml

route DNS to the tunnel. [web:62]

4.4 Configure ingress (hostnames → local services)
Create ~/.cloudflared/config.yml with:

tunnel UUID

credentials-file path

ingress rules mapping hostnames to services. [web:62]

Example: expose a web app running on localhost:8080:

text
tunnel: <TUNNEL-UUID>
credentials-file: /home/<user>/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: app.yourdomain.com
    service: http://localhost:8080
  - service: http_status:404
Validate config (recommended):

bash
cloudflared tunnel ingress validate
Cloudflare documents validating ingress rules with this command. [web:63]

4.5 Route DNS to the tunnel
For locally-managed tunnels, Cloudflare describes routing by creating a CNAME that points traffic to your tunnel subdomain (<UUID>.cfargotunnel.com) or by using their routing commands depending on the method you chose. [web:62]

If you used the dashboard “remote-managed” approach, the UI usually handles DNS routing steps for you (follow what it shows). [web:47]

4.6 Run the tunnel
Run it in the foreground:

bash
cloudflared tunnel run <TUNNEL-NAME-OR-UUID>
Then set it up as a service so it survives reboots (Cloudflare provides service instructions in their guides / tunnel setup output). [web:62]

5) Example: publish a Dockerized service
If a container exposes port 8080 on the host, you can route the tunnel to http://localhost:8080 (as in the ingress example). [web:62]

Quick test container:

bash
docker run --rm -p 8080:80 nginx:alpine
Then browse https://app.yourdomain.com once DNS + tunnel are in place.

6) Troubleshooting
Tunnel works but you get 502/504: your origin service is not reachable at the service: URL you configured (wrong port, app not running, bound only to a container network, etc.). [web:61][web:62]

Don’t see SSH after enabling UFW: you probably enabled UFW before allowing SSH; Cloudflare/DigitalOcean-style guidance is to allow SSH first to avoid lockout. [web:52][web:58]

Want to expose multiple apps: add more hostname entries in ingress, each pointing to the right local service. [web:62]