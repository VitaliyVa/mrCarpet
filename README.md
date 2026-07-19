# MrCarpet - E-commerce Platform

A Django-based e-commerce platform for carpet sales with payment integration, order management, and admin panel.

## Features

- 🛒 Shopping cart and checkout system
- 💳 Payment integration (LiqPay)
- 📦 Order management
- 📧 Newsletter system
- 🔐 User authentication and password reset
- 📱 Responsive design
- 🚀 Production-ready with Docker and Nginx
- 🔒 HTTPS/SSL support with Let's Encrypt

## Tech Stack

- **Backend**: Django 4.2.7, Django REST Framework
- **Server**: Gunicorn
- **Web Server**: Nginx
- **Database**: SQLite (production) / PostgreSQL (optional)
- **Containerization**: Docker, Docker Compose
- **Payment**: LiqPay integration
- **Deployment**: GitHub Actions (CI/CD)

## Prerequisites

- Docker and Docker Compose
- Python 3.9+ (for local development)
- Git
- Domain name with DNS configured (for production)

## Quick Start

### Development

1. Clone the repository:
```bash
git clone https://github.com/VitaliyVa/mrCarpet.git
cd mrCarpet
```

2. Create `.env` file:
```bash
cp .env.example .env
# Edit .env with your settings
```

3. Run with Docker Compose:
```bash
docker compose up -d
```

4. Create superuser:
```bash
docker compose exec web python manage.py createsuperuser
```

5. Access the application:
- Frontend: http://localhost:8000
- Admin: http://localhost:8000/admin

### Production Deployment

1. **Configure Environment Variables**

Set the following environment variables on your server:
- `NOVA_POSHTA_API_KEY` - Nova Poshta API key
- `EMAIL_HOST_USER` - Email for sending notifications
- `EMAIL_HOST_PASSWORD` - Email password
- `LIQPAY_PUBLIC_KEY` - LiqPay public key
- `LIQPAY_PRIVATE_KEY` - LiqPay private key
- `REPLICATE_API_TOKEN` - Replicate API token (admin image generation)

2. **Configure DNS**

Point your domain to the server IP:
- Create A record: `@` → `YOUR_SERVER_IP`
- Create A record: `www` → `YOUR_SERVER_IP`

3. **Deploy**

The project uses GitHub Actions for automatic deployment. Push to `main` branch to trigger deployment.

Or deploy manually:
```bash
git clone https://github.com/VitaliyVa/mrCarpet.git
cd mrCarpet

# Create SSL certificates (first time only)
docker compose -f docker-compose.prod.yml run --rm certbot
# Start services
docker compose -f docker-compose.prod.yml up -d

# Create superuser
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

### Production SQLite safety (read this)

The app uses SQLite with **WAL** (`db.sqlite3` + `db.sqlite3-wal` + `db.sqlite3-shm`). Those files must **never** be committed or overwritten by `git pull`.

- `.gitignore` ignores `*.sqlite3`, `*.sqlite3-wal`, `*.sqlite3-shm`
- Deploy backs up and restores the live DB around `git pull` (see `.github/workflows/deploy.yml`)
- Local incident notes / runbooks live under `ops/` (gitignored, like `docs/`)

## SSL/HTTPS Setup

The project includes automatic SSL certificate generation and renewal:

1. **First-time setup**:
   - Certificates are automatically generated via Certbot
   - SSL configuration files are created by `nginx-init` service

2. **Certificate renewal**:
   - Automatic renewal via `certbot-renew` service (runs every 12 hours)
   - Nginx reloads after certificate renewal

3. **Manual renewal**:
```bash
docker compose -f docker-compose.prod.yml run --rm certbot renew
docker compose -f docker-compose.prod.yml restart nginx
```

## Project Structure

```
mrCarpet/
├── blog/              # Blog/articles app
├── cart/              # Shopping cart functionality
├── catalog/           # Product catalog
├── config/            # Nginx and server configurations
├── core/              # Django project settings
├── nova_poshta/       # Nova Poshta shipping integration
├── order/             # Order management
├── payment/           # Payment processing (LiqPay)
├── project/           # Core project models and utilities
├── scripts/           # Ops / recovery helpers
├── users/             # User authentication and profiles
├── templates/         # HTML templates
├── static/            # Static files (CSS, JS)
└── docker-compose.prod.yml  # Production Docker Compose config
```

## Docker Services

- **web**: Django application (Gunicorn)
- **nginx**: Reverse proxy and static file server
- **nginx-init**: Creates SSL configuration files
- **certbot**: SSL certificate generation
- **certbot-renew**: Automatic certificate renewal

## Environment Variables

Create a `.env` file or set environment variables:

```env
DEBUG=False
ALLOWED_HOSTS=mrcarpet24.com,www.mrcarpet24.com
# LiqPay sandbox відв'язаний від DEBUG. false = бойові платежі (потрібні бойові ключі!)
LIQPAY_SANDBOX=true
SECRET_KEY=your_django_secret_key
NOVA_POSHTA_API_KEY=your_key
UKR_POSHTA_BEARER=your_ukrposhta_bearer_token
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_password
LIQPAY_PUBLIC_KEY=your_public_key
LIQPAY_PRIVATE_KEY=your_private_key
REPLICATE_API_TOKEN=your_replicate_token
# Тимчасові CSRF origins для локальних webhook-тестів (ngrok тощо):
# CSRF_EXTRA_TRUSTED_ORIGINS=https://xxxx.ngrok-free.app
```

## Frontend Build (Webpack)

Прод роздає закомічені бандли зі `static/source/pages/` — **білд на деплої не запускається**.
Джерела фронтенду живуть у `static/development/`. Після будь-якої зміни JS/SCSS:

```bash
cd static
npm run build   # збирає development/ -> source/pages/
# закомітити і source/pages/, і development/
```

CI-workflow `verify-static.yml` перевіряє, що закомічений бандл відповідає збірці
з сорсів, і червоніє при розсинхроні (наприклад, якщо правили компільовані файли
руками або забули перезібрати). Потрібен Node 16 локально? Ні — будь-який Node,
але на Node 17+ потрібен `NODE_OPTIONS=--openssl-legacy-provider` (webpack 4 + OpenSSL 3).
Не редагуйте `static/source/pages/**` вручну.

## Common Commands

### Docker Compose

```bash
# Start services
docker compose -f docker-compose.prod.yml up -d

# Stop services
docker compose -f docker-compose.prod.yml down

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Restart service
docker compose -f docker-compose.prod.yml restart nginx

# Execute command in container
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

### Django Management

```bash
# Run migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

# Collect static files
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic

# Create superuser
docker compose -f docker-compose.prod.yml exec -it web python manage.py createsuperuser

# Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell
```

## CI/CD

GitHub Actions workflow automatically:
- Builds Docker images
- Deploys to production server via SSH
- Runs migrations
- Collects static files
- Restarts services

Configure GitHub Secrets:
- `SSH_PRIVATE_KEY` - SSH private key for server access
- `SERVER_HOST` - Server IP or domain
- `SERVER_USER` - SSH username

## Troubleshooting

### SSL Certificate Issues

```bash
# Check certificate status
docker compose -f docker-compose.prod.yml run --rm certbot certificates

# Force certificate renewal
docker compose -f docker-compose.prod.yml run --rm certbot renew --force-renewal

# Check Nginx configuration
docker compose -f docker-compose.prod.yml exec nginx nginx -t
```

### Permission Issues

```bash
# Fix certbot permissions
sudo chown -R $USER:$USER config/certbot
sudo chmod -R 755 config/certbot
```

### Static Files Not Loading

```bash
# Recollect static files
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

# Check static files location
docker compose -f docker-compose.prod.yml exec nginx ls -la /app/static_root
```

## Security

- Root SSH login is disabled
- HTTPS enforced with automatic redirect
- CSRF protection enabled
- Secure SSL/TLS configuration
- Environment variables for sensitive data

## License

This project is proprietary software.

## Support

For issues and questions, please contact the development team.
