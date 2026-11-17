# Deploying NairobiFloodWatch: Azure VM + Netlify + Namecheap

What you end up with:

| Piece | Where | Address |
|---|---|---|
| API, database, hourly weather collection, photos | One Azure Ubuntu VM | `https://api.example.co.ke` |
| Dashboard (map, report form, staff pages) | Netlify | `https://example.co.ke` and `https://www.example.co.ke` |
| Domain | Namecheap DNS | points to both |

Replace `example.co.ke` with your domain everywhere below. Commands in grey boxes run on
the **server** unless marked *Windows*.

Have ready: your Azure login, Namecheap login, a GitHub login (for Netlify), the email
for the first administrator, your NASA Earthdata username/password, and your
OpenRouteService key.

---

## 1. Create the virtual machine (Azure portal)

Azure portal → **Virtual machines → Create → Azure virtual machine**:

- **Resource group:** new, `floodwatch-rg`
- **Name:** `floodwatch-vm`
- **Region:** *South Africa North* (closest to Nairobi). If your subscription does not allow
  it, use *UK South* or *West Europe*.
- **Image:** Ubuntu Server 24.04 LTS (x64)
- **Size:** `Standard_B2s` (2 vCPU, 4 GB). `B1ms` (2 GB) works but is tight.
- **Authentication:** SSH public key, username `azureuser`, *Generate new key pair*, name
  `floodwatch-key`. Download the `.pem` when asked and keep it safe (e.g.
  `C:\Users\<you>\.ssh\floodwatch-key.pem`).
- **Inbound ports:** allow SSH (22), HTTP (80), HTTPS (443).
- **Disks:** Standard SSD, default size (30 GB is plenty).
- **Networking → Public IP:** create new, **SKU Standard, assignment Static** (the address
  must not change).
- **Management:** leave **Auto-shutdown off** (the API must run all night).

Create, then copy the VM's **public IP address**.

Then lock SSH to your own connection: VM → **Networking → Network settings** → the
inbound rule for port 22 → *Source: My IP address*. (Ports 80/443 stay open to everyone.)

Optional but wise: **Cost Management → Budgets** → a monthly budget with an email alert.

## 2. Point the API name at the VM (Namecheap)

Namecheap → Domain List → your domain → **Manage → Advanced DNS → Add new record**:

| Type | Host | Value | TTL |
|---|---|---|---|
| A Record | `api` | *VM public IP* | Automatic |

(The website records come in step 10.) DNS usually takes 5–30 minutes.

## 3. Connect to the server

*Windows* (PowerShell):

```powershell
icacls $env:USERPROFILE\.ssh\floodwatch-key.pem /inheritance:r /grant:r "$($env:USERNAME):(R)"
ssh -i $env:USERPROFILE\.ssh\floodwatch-key.pem azureuser@<VM-IP>
```

## 4. Install the system software

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3.12-venv git nginx certbot python3-certbot-nginx \
    postgresql postgresql-16-postgis-3 ufw unattended-upgrades
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw --force enable
timedatectl                      # "System clock synchronized: yes" (needed for collection)
sudo adduser --system --group --home /srv/nairobifloodwatch floodwatch
```

## 5. Create the database

Choose a strong database password (letters and digits only keeps the URL simple):

```bash
sudo -u postgres psql -c "CREATE USER floodwatch WITH PASSWORD 'CHOOSE-A-STRONG-PASSWORD';"
sudo -u postgres createdb -O floodwatch nairobifloodwatch
sudo -u postgres psql -d nairobifloodwatch -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

## 6. Get the code, Python environments and runtime data

Merge the open pull request into `main` on GitHub first, then:

```bash
sudo -u floodwatch git clone https://github.com/BillyKibet-dev/Predictive-Flood-Modelling-System.git /srv/nairobifloodwatch
cd /srv/nairobifloodwatch
sudo -u floodwatch python3 -m venv .venv
sudo -u floodwatch .venv/bin/pip install -r requirements.txt
sudo -u floodwatch python3 -m venv .venv-model-v1
sudo -u floodwatch .venv-model-v1/bin/pip install -r requirements-model-v1.txt
```

The git-ignored runtime data (research model inputs, weather/rainfall history) travels as
one verified bundle. *Windows*, in the project folder:

```powershell
python deploy/scripts/pack_runtime_data.py
scp -i $env:USERPROFILE\.ssh\floodwatch-key.pem deploy/out/runtime-data.tar.gz azureuser@<VM-IP>:/tmp/
```

Server:

```bash
sudo bash /srv/nairobifloodwatch/deploy/scripts/install_runtime_data.sh /tmp/runtime-data.tar.gz
rm /tmp/runtime-data.tar.gz
```

## 7. Configure and initialise the API

```bash
sudo mkdir -p /etc/nairobifloodwatch
sudo cp deploy/examples/application.env.example /etc/nairobifloodwatch/application.env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"     # copy this for SECRET_KEY
sudo nano /etc/nairobifloodwatch/application.env
```

Fill in (leave everything else as it is):

```text
DATABASE_URL=postgresql://floodwatch:CHOOSE-A-STRONG-PASSWORD@localhost:5432/nairobifloodwatch
SECRET_KEY=<the value printed above>
FRONTEND_URL=https://example.co.ke,https://www.example.co.ke,https://<your-site>.netlify.app
EARTHDATA_USERNAME=<NASA Earthdata username>
EARTHDATA_PASSWORD=<NASA Earthdata password>
OPENROUTESERVICE_API_KEY=<your key>
```

(You can come back to `FRONTEND_URL` once Netlify has given the site its name.)

```bash
sudo chown root:floodwatch /etc/nairobifloodwatch/application.env
sudo chmod 640 /etc/nairobifloodwatch/application.env
```

Create the tables, first administrator and outlines (prompts for the admin password):

```bash
cd /srv/nairobifloodwatch
run() { sudo -u floodwatch bash -c "set -a; . /etc/nairobifloodwatch/application.env; set +a; cd /srv/nairobifloodwatch; .venv/bin/python -m $*"; }
run src.scripts.init_db --admin-email you@example.com --admin-name "Administrator"
run src.scripts.migrate_model_v1 --schema public
run src.scripts.migrate_environmental --schema public
run src.scripts.migrate_reports --schema public
run src.scripts.migrate_operational_sources --schema public
run src.scripts.load_boundaries
```

Start the API as a service:

```bash
sudo cp deploy/examples/nairobifloodwatch-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nairobifloodwatch-api
curl -s localhost:8000/health        # {"status":"online", ...}
journalctl -u nairobifloodwatch-api -n 30 --no-pager   # "automatic weather collection=True"
```

## 8. HTTPS for the API (nginx + Let's Encrypt)

Wait until `api.example.co.ke` resolves to the VM (`nslookup api.example.co.ke` on Windows), then:

```bash
sudo certbot certonly --nginx -d api.example.co.ke -m you@example.com --agree-tos -n
sudo cp deploy/examples/nginx-floodwatch-proxy.conf /etc/nginx/snippets/floodwatch-proxy.conf
sudo sed 's/api\.example\.co\.ke/api.YOUR-DOMAIN/g' deploy/examples/nginx-nairobifloodwatch.conf \
    | sudo tee /etc/nginx/sites-available/nairobifloodwatch >/dev/null
sudo ln -sf /etc/nginx/sites-available/nairobifloodwatch /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Check from *Windows*: open `https://api.example.co.ke/health` and `https://api.example.co.ke/docs`.
Certificates renew automatically (`systemctl list-timers | grep certbot`).

## 9. (Optional) the original eight-zone forecast archive

The staff Weather page's *original eight-zone forecast archive* is filled by a daily job:

```bash
sudo cp /etc/nairobifloodwatch/application.env /etc/nairobifloodwatch/collection.env
sudo cp deploy/examples/nairobifloodwatch-collection.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now nairobifloodwatch-collection.timer
```

## 10. Dashboard on Netlify

1. app.netlify.com → **Add new site → Import an existing project → GitHub** → choose
   `Predictive-Flood-Modelling-System`, branch `main`. Netlify reads `netlify.toml`
   (base `dashboard`, build `npm ci && npm run build`, publish `dist`). Don't change them.
2. **Site configuration → Environment variables → Add:** `VITE_API_BASE_URL` =
   `https://api.example.co.ke`. Then **Deploys → Trigger deploy**.
3. **Domain management → Add a domain:** `example.co.ke` (Netlify also adds `www`).
   Netlify shows the DNS values to use; in Namecheap **Advanced DNS** delete the parking
   records (the `www` CNAME to *parkingpage* and the URL redirect for `@`) and add:

   | Type | Host | Value |
   |---|---|---|
   | A Record | `@` | the load-balancer IP Netlify shows (usually `75.2.60.5`) |
   | CNAME Record | `www` | `<your-site>.netlify.app.` |

   Keep the `api` A record from step 2.
4. When Netlify shows the domain as verified, **HTTPS → Verify DNS → Provision certificate**.
5. Put the final addresses in the API's `FRONTEND_URL` (step 7) and
   `sudo systemctl restart nairobifloodwatch-api`.

## 11. Check everything

- `https://example.co.ke` opens the map; pins are coloured (grey for up to an hour after
  first start, until the first collection at minute 5).
- Sign in as the administrator → **System**: API *Responding*, weather *fresh*, model *used*.
- **Users:** add your officers.
- Report form: send a test report with your location and a photo; it reaches **Reports**.
  Delete-worthy test data can be marked *Resolved*.
- **Check a route** finds places and returns a route.
- Switch **SW** and back.
- Browser console (F12) shows no CORS errors. If it does, `FRONTEND_URL` is missing that
  exact address (scheme included, no trailing slash).

## 12. Backups and updates

Nightly backup at 01:30 UTC (database + weather stores + photos, kept 14 days):

```bash
sudo install -m 750 deploy/scripts/backup.sh /usr/local/bin/floodwatch-backup
echo '30 1 * * * root /usr/local/bin/floodwatch-backup >> /var/log/floodwatch-backup.log 2>&1' | sudo tee /etc/cron.d/nairobifloodwatch-backup
sudo /usr/local/bin/floodwatch-backup        # first run now
```

These copies live on the same VM. Copy one off it now and then (*Windows*:
`scp -i ... azureuser@<VM-IP>:/var/backups/nairobifloodwatch/db-*.dump .`), or enable
**VM → Backup** in Azure for off-machine copies.

Deploying a new version (Netlify rebuilds the dashboard by itself on every push to `main`):

```bash
cd /srv/nairobifloodwatch
sudo -u floodwatch git pull
sudo -u floodwatch .venv/bin/pip install -r requirements.txt
run src.scripts.migrate_reports --schema public      # whenever a release adds a migration
sudo systemctl restart nairobifloodwatch-api
```

## Troubleshooting

| Symptom | Look at |
|---|---|
| API won't start | `journalctl -u nairobifloodwatch-api -n 80 --no-pager` |
| 502 from `api.` | API not running on 127.0.0.1:8000 (`systemctl status nairobifloodwatch-api`) |
| Grey pins after 2 hours | System page; then the log for `collection`; check `timedatectl` |
| NASA rainfall missing | `EARTHDATA_*` in the env file; NASA requests are sequential and can be slow |
| Photo upload fails | nginx `client_max_body_size` for the photo location (9m) |
| CORS error in browser | `FRONTEND_URL` exact match, then restart the API |
| Certificate error on `api.` | `sudo certbot renew --dry-run` |
