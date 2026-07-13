# CEMS AWS EC2 Deployment Guide

This guide describes the recommended AWS deployment for CEMS.

Recommended setup:

- One EC2 Ubuntu server runs CEMS with Docker Compose.
- Amazon RDS PostgreSQL stores production election data.
- Nginx serves HTTPS and proxies to Django/Gunicorn.
- A domain such as `cems.school.edu` points to the EC2 Elastic IP.

This is simpler than ECS/EKS and safer than storing the production database only
inside an EC2 Docker volume.

## Architecture

```text
Users
  |
  | HTTPS
  v
Domain / DNS
  |
  v
EC2 Elastic IP
  |
  v
EC2 Ubuntu Server
  - Docker Engine
  - Nginx container, ports 80/443
  - Django/Gunicorn web container
  - static/media/log Docker volumes
  |
  | private VPC traffic, port 5432
  v
Amazon RDS PostgreSQL
```

## AWS Resources

Use these defaults for a pilot or normal school election:

- EC2: Ubuntu Server 24.04 LTS
- Instance type: `t3.medium` minimum
- EC2 disk: 60-80 GB gp3
- RDS: PostgreSQL 16
- RDS size: start with `db.t4g.micro` or `db.t4g.small` for pilot; use larger if load testing shows pressure
- RDS public access: `No`
- RDS automated backups: 7-14 days
- Elastic IP: associated to the EC2 instance

For campus-wide election day, prefer:

- EC2: `t3.large` or better
- RDS: `db.t4g.small` or better
- A manual RDS snapshot before opening voting

## Security Groups

Create two security groups.

### EC2 Security Group

Inbound:

| Type | Port | Source |
| --- | --- | --- |
| SSH | 22 | Your admin IP only |
| HTTP | 80 | `0.0.0.0/0`, `::/0` |
| HTTPS | 443 | `0.0.0.0/0`, `::/0` |

Outbound:

- Allow default outbound traffic, or at minimum allow HTTPS and PostgreSQL to RDS.

### RDS Security Group

Inbound:

| Type | Port | Source |
| --- | --- | --- |
| PostgreSQL | 5432 | EC2 security group only |

Do not expose RDS publicly.

## 1. Create RDS PostgreSQL

In the AWS console:

1. Open RDS.
2. Choose **Create database**.
3. Choose **Standard create**.
4. Engine: PostgreSQL.
5. Version: PostgreSQL 16.
6. DB identifier: `cems-prod`.
7. Database name: `cems`.
8. Master username: `cems`.
9. Generate and store a strong password.
10. Public access: `No`.
11. VPC: same VPC as the EC2 instance.
12. Security group: the RDS security group above.
13. Enable automated backups.
14. Create the DB.

After creation, copy the RDS endpoint. It will look like:

```text
cems-prod.xxxxxxxxxxxx.ap-southeast-1.rds.amazonaws.com
```

## 2. Launch EC2

1. Open EC2.
2. Launch an Ubuntu Server 24.04 LTS instance.
3. Choose `t3.medium` or larger.
4. Use the EC2 security group above.
5. Allocate and associate an Elastic IP.
6. Add a DNS `A` record pointing your domain to the Elastic IP.

Example:

```text
cems.school.edu -> EC2 Elastic IP
```

## 3. Install Docker On EC2

SSH into the instance:

```bash
ssh ubuntu@cems.school.edu
```

Install Docker Engine and the Compose plugin:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git ca-certificates curl gnupg openssl

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and log back in so group membership takes effect.

Check:

```bash
docker --version
docker compose version
```

## 4. Clone CEMS

```bash
sudo mkdir -p /opt/cems
sudo chown "$USER":"$USER" /opt/cems
git clone https://github.com/GhanyDC/CSU-CEMS.git /opt/cems
cd /opt/cems
cp .env.example .env
```

## 5. Create AWS Compose File

The repo's `docker-compose.prod.yml` includes a local PostgreSQL container.
For AWS, use RDS instead.

Create an AWS-specific compose file:

```bash
cp docker-compose.prod.yml docker-compose.aws.yml
nano docker-compose.aws.yml
```

Edit `docker-compose.aws.yml`:

1. Remove the entire `db:` service.
2. Remove the top-level `postgres_data:` volume if it is unused.
3. Remove this block from `web`:

```yaml
depends_on:
  db:
    condition: service_healthy
```

4. In `web.environment`, change:

```yaml
POSTGRES_HOST: db
```

to:

```yaml
POSTGRES_HOST: ${POSTGRES_HOST}
```

Keep `web`, `nginx`, `static_volume`, `media_volume`, and `logs_volume`.

## 6. Configure `.env`

Edit:

```bash
nano .env
```

Use production values:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=False
DJANGO_SECRET_KEY=replace-with-generated-secret
DJANGO_ALLOWED_HOSTS=cems.school.edu
DJANGO_CSRF_TRUSTED_ORIGINS=https://cems.school.edu

POSTGRES_DB=cems
POSTGRES_USER=cems
POSTGRES_PASSWORD=replace-with-rds-password
POSTGRES_HOST=cems-prod.xxxxxxxxxxxx.ap-southeast-1.rds.amazonaws.com
POSTGRES_PORT=5432

CEMS_MAX_FAILED_ATTEMPTS=5
CEMS_LOCKOUT_MINUTES=30

GUNICORN_WORKERS=3
DJANGO_RUN_MIGRATIONS=1
DJANGO_COLLECTSTATIC=1
```

Generate `DJANGO_SECRET_KEY`:

```bash
openssl rand -base64 48
```

Never commit `.env`.

## 7. Configure Nginx Domain

Edit:

```bash
nano docker/nginx.conf
```

Replace the existing `server_name` values with your real domain:

```nginx
server_name cems.school.edu;
```

Do this in both the port 80 and port 443 server blocks.

## 8. Configure HTTPS Certificate

The production compose file mounts host certificates from:

```text
/opt/cems/certs
```

Install Certbot:

```bash
sudo apt install -y certbot
```

Temporarily make sure nothing is using port 80, then request a certificate:

```bash
sudo certbot certonly --standalone -d cems.school.edu
```

Copy certificates to the path used by Docker:

```bash
sudo mkdir -p /opt/cems/certs
sudo cp /etc/letsencrypt/live/cems.school.edu/fullchain.pem /opt/cems/certs/fullchain.pem
sudo cp /etc/letsencrypt/live/cems.school.edu/privkey.pem /opt/cems/certs/privkey.pem
sudo chmod 600 /opt/cems/certs/privkey.pem
```

Renewal note: after Certbot renews certificates, copy the renewed files again
and restart Nginx:

```bash
docker compose -f /opt/cems/docker-compose.aws.yml restart nginx
```

## 9. Start CEMS

```bash
cd /opt/cems
docker compose -f docker-compose.aws.yml up -d --build
docker compose -f docker-compose.aws.yml ps
```

Expected services:

- `web`
- `nginx`

There should be no local `db` container when using RDS.

## 10. Initialize Production Data

Run migrations and collectstatic are already enabled in `.env`, but it is safe
to run these explicitly:

```bash
docker compose -f docker-compose.aws.yml exec web python manage.py migrate
docker compose -f docker-compose.aws.yml exec web python manage.py collectstatic --noinput
docker compose -f docker-compose.aws.yml exec web python manage.py seed_colleges
```

Create the first admin:

```bash
docker compose -f docker-compose.aws.yml exec web \
  python manage.py create_admin \
  --username eb_head \
  --role electoral_board_head \
  --display-name "Electoral Board Head"
```

Do not run `generate_pilot_data` in production.

## 11. Verify Deployment

Health check:

```bash
curl https://cems.school.edu/api/health/
```

Production checks:

```bash
docker compose -f docker-compose.aws.yml exec web python manage.py check
docker compose -f docker-compose.aws.yml exec web python manage.py check --deploy
```

Open:

```text
https://cems.school.edu/
https://cems.school.edu/election-admin/login/
```

Confirm:

- Login page loads over HTTPS.
- Admin login works.
- Admin panel loads.
- Colleges are seeded.
- Registrar batch upload works in a rehearsal election.
- Student registration works.
- Voter roll can be finalized.
- A test election can be started, voted in, closed, and published.

## 12. Backups

RDS automated backups should be enabled from the RDS console.

Before election day:

1. Take a manual RDS snapshot.
2. Export a logical backup:

```bash
docker compose -f docker-compose.aws.yml exec web \
  python manage.py check
```

From a machine with `pg_dump` and access to RDS, or from the EC2 host if
PostgreSQL client tools are installed:

```bash
PGPASSWORD='replace-with-rds-password' pg_dump \
  -h cems-prod.xxxxxxxxxxxx.ap-southeast-1.rds.amazonaws.com \
  -U cems \
  -d cems \
  > cems_backup_$(date +%Y%m%d_%H%M).sql
```

Keep backups encrypted and access-controlled.

## 13. Updating The App

```bash
cd /opt/cems
git pull origin master
docker compose -f docker-compose.aws.yml up -d --build
docker compose -f docker-compose.aws.yml exec web python manage.py migrate
docker compose -f docker-compose.aws.yml exec web python manage.py collectstatic --noinput
docker compose -f docker-compose.aws.yml ps
curl https://cems.school.edu/api/health/
```

## 14. Troubleshooting

### `DisallowedHost`

Update `.env`:

```env
DJANGO_ALLOWED_HOSTS=cems.school.edu
```

Then restart:

```bash
docker compose -f docker-compose.aws.yml restart web
```

### CSRF Errors

Make sure:

```env
DJANGO_CSRF_TRUSTED_ORIGINS=https://cems.school.edu
```

Then restart `web`.

### HTTPS Redirect Loop

Confirm Nginx sends:

```nginx
proxy_set_header X-Forwarded-Proto https;
```

The repo's `docker/nginx.conf` already includes this.

### RDS Connection Fails

Check:

- RDS is in the same VPC.
- RDS public access is disabled.
- RDS security group allows PostgreSQL from the EC2 security group.
- `.env` has the correct `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`.

Test from EC2 if `psql` is installed:

```bash
PGPASSWORD='replace-with-rds-password' psql \
  -h cems-prod.xxxxxxxxxxxx.ap-southeast-1.rds.amazonaws.com \
  -U cems \
  -d cems \
  -c 'select 1;'
```

### Containers Will Not Start

```bash
docker compose -f docker-compose.aws.yml ps
docker compose -f docker-compose.aws.yml logs --tail=100 web
docker compose -f docker-compose.aws.yml logs --tail=100 nginx
```

## Pre-Election Checklist

- [ ] `.env` uses `config.settings.production`.
- [ ] `DEBUG=False`.
- [ ] `DJANGO_SECRET_KEY` is unique and secret.
- [ ] RDS is private and backed up.
- [ ] EC2 SSH is limited to admin IPs.
- [ ] HTTPS works.
- [ ] `/api/health/` returns success.
- [ ] Admin accounts are real accounts, not pilot credentials.
- [ ] Colleges are seeded.
- [ ] Registrar batch workflow has been tested.
- [ ] Student registration workflow has been tested.
- [ ] College election scope rules have been tested.
- [ ] Voter roll finalization has been tested.
- [ ] A full mock election has been completed.
- [ ] Manual RDS snapshot taken.
- [ ] Recovery process has been rehearsed.

## References

- AWS RDS getting started: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_GettingStarted.html>
- AWS RDS PostgreSQL with EC2: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_GettingStarted.CreatingConnecting.PostgreSQL.html>
- AWS security groups: <https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html>
- AWS security group rule reference: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html>
- AWS Elastic IP addresses: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html>
- Docker Engine on Ubuntu: <https://docs.docker.com/engine/install/ubuntu/>
