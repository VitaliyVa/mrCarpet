"""
Production infra files that tests can check without a server.

* nginx config from the repo never reached prod: the config is a single-file
  bind mount, git pull writes a new inode, the running container kept the old
  one and `nginx -s reload` reloaded the stale file. Deploy now checks the
  pulled config with `nginx -t` and recreates the container only if it passes.
* gunicorn ran 1 worker x 2 threads, so bursts queued in pairs.
"""

import re
from pathlib import Path

import yaml
from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _compose():
    return yaml.safe_load(_read("docker-compose.prod.yml"))


def _deploy_script():
    wf = yaml.safe_load(_read(".github/workflows/deploy.yml"))
    steps = wf["jobs"]["deploy"]["steps"]
    return next(s["run"] for s in steps if s.get("name") == "Deploy to server")


class GunicornConcurrencyTests(SimpleTestCase):
    def setUp(self):
        self.command = _compose()["services"]["web"]["command"]

    def _arg(self, name):
        m = re.search(rf"--{name} (\d+)", self.command)
        self.assertIsNotNone(m, name)
        return int(m.group(1))

    def test_more_than_one_process(self):
        self.assertGreaterEqual(self._arg("workers"), 2)

    def test_stays_conservative_for_sqlite(self):
        self.assertLessEqual(self._arg("workers"), 3)
        self.assertLessEqual(self._arg("workers") * self._arg("threads"), 12)

    def test_long_timeout_kept(self):
        """Admin actions and social renders run long inside a request."""
        self.assertEqual(self._arg("timeout"), 300)

    def test_sqlite_is_in_wal_mode(self):
        """Several processes only work on SQLite because of WAL + busy_timeout."""
        src = _read("core/settings.py")
        self.assertIn("PRAGMA journal_mode=WAL;", src)
        self.assertIn("PRAGMA busy_timeout=30000;", src)


class DeployAppliesNginxConfigTests(SimpleTestCase):
    VALIDATE = "docker compose -f docker-compose.prod.yml run --rm --no-deps -T nginx nginx -t </dev/null"
    RECREATE = "docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate nginx"

    def setUp(self):
        self.script = _deploy_script()
        self.commands = [
            line.strip()
            for line in self.script.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_no_stale_reload(self):
        self.assertFalse([c for c in self.commands if "nginx -s reload" in c])

    def test_validates_after_pull_and_before_any_up(self):
        validate = self.script.index(self.VALIDATE)
        self.assertGreater(validate, self.script.index("git pull origin main"))
        first_up = self.script.index("docker compose -f docker-compose.prod.yml up -d")
        self.assertLess(validate, first_up)

    def test_recreate_only_when_config_is_valid(self):
        recreate = self.script.index(self.RECREATE)
        guard = self.script.rindex('if [ "$NGINX_CONFIG_OK" = "1" ]; then', 0, recreate)
        between = self.script[guard:recreate]
        self.assertNotIn("fi\n", between)
        self.assertGreater(recreate, self.script.index("Running migrations..."))

    def test_invalid_config_never_restarts_or_recreates_nginx(self):
        # the catch-all `up -d` falls back to --no-recreate
        self.assertIn("up -d --no-recreate", self.script)
        # every healthcheck restart is behind the same guard
        restarts = [i for i, c in enumerate(self.commands) if c.endswith("restart nginx")]
        self.assertTrue(restarts)
        for i in restarts:
            self.assertEqual(self.commands[i - 1], 'if [ "$NGINX_CONFIG_OK" = "1" ]; then')

    def test_invalid_config_fails_the_workflow(self):
        tail = self.script[self.script.index("docker image prune -f"):]
        self.assertIn('if [ "$NGINX_CONFIG_OK" != "1" ]; then', tail)
        self.assertIn("exit 1", tail)


class NginxConfigTests(SimpleTestCase):
    def setUp(self):
        self.site = _read("config/mrcarpet.docker")
        self.main = _read("config/nginx-main.conf")
        self.nginx = _compose()["services"]["nginx"]

    def _location(self, head):
        start = self.site.index(head)
        return self.site[start : self.site.index("\n    }", start)]

    def test_compose_mounts_the_repo_files(self):
        volumes = self.nginx["volumes"]
        self.assertIn("./config/nginx-main.conf:/etc/nginx/nginx.conf:ro", volumes)
        self.assertTrue(any(v.startswith("./config/mrcarpet.docker:/etc/nginx/conf.d/default.conf") for v in volumes))
        self.assertIn("include /etc/nginx/conf.d/*.conf;", self.main)
        self.assertIn("include       /etc/nginx/mime.types;", self.main)

    def test_no_static_upstream(self):
        """A static upstream pins web's IP at start and 502s after web is recreated."""
        self.assertNotRegex(self.site, r"(?m)^\s*upstream\s")
        self.assertIn("resolver 127.0.0.11", self.site)
        self.assertIn("set $django_upstream web:8000;", self.site)

    def test_one_cache_control_per_static_response(self):
        for head in ("location ^~ /static/source/pages/ {", "location /static/ {", "location /media/ {"):
            block = self._location(head)
            self.assertNotIn("expires", block, head)
            self.assertEqual(block.count("add_header Cache-Control"), 1, head)

    def test_page_bundles_revalidate(self):
        block = self._location("location ^~ /static/source/pages/ {")
        self.assertIn("alias /app/static_root/source/pages/;", block)
        self.assertNotIn("immutable", block)
        self.assertIn("must-revalidate", block)

    def test_favicon_served_from_collected_static(self):
        block = self._location("location = /favicon.ico {")
        self.assertIn("alias /app/static_root/utils/assets/favicon.ico;", block)
        self.assertTrue((ROOT / "static/utils/assets/favicon.ico").is_file())

    def test_media_types_keep_video(self):
        """The types block replaces mime.types inside /media/."""
        block = self._location("location /media/ {")
        for line in ("video/mp4 mp4;", "image/webp webp;", "image/jpeg jpg jpeg;", "image/png png;"):
            self.assertIn(line, block)
