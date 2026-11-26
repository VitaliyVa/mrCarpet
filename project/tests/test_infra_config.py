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


STOP_WEB = "docker compose -f docker-compose.prod.yml stop web || true"
START_WEB = "docker compose -f docker-compose.prod.yml up -d web\n"
PRE_VALIDATE = 'echo "Validating nginx config of the incoming commit'


def _validator_block(script):
    start = script.index(PRE_VALIDATE)
    end = script.index("nginx -t </dev/null", start) + len("nginx -t </dev/null")
    return script[start:end]


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

    def test_validates_incoming_config_before_stop_and_any_up(self):
        """nginx -t runs on the incoming commit while the site is still up."""
        validate = self.script.index(PRE_VALIDATE)
        self.assertLess(validate, self.script.index(STOP_WEB))
        self.assertLess(validate, self.script.index(START_WEB))
        # validated files come from the export of the incoming commit
        block = _validator_block(self.script)
        self.assertIn('"$NEXT_DIR/config/mrcarpet.docker:', block)
        self.assertIn('"$NEXT_DIR/config/nginx-main.conf:', block)

    def test_revalidates_pulled_config_when_it_may_differ(self):
        """Pulled tree != validated tree (newer push, compose change): check
        again with the real compose mounts, still before any up."""
        validate = self.script.index(self.VALIDATE)
        self.assertGreater(validate, self.script.index("git pull origin main"))
        self.assertLess(validate, self.script.index(START_WEB))
        guard = self.script.rindex('if [ "$PULLED_HEAD" != "$NEW_HEAD" ]', 0, validate)
        self.assertNotIn("\n        fi\n", self.script[guard:validate])

    def test_validator_mirrors_compose_nginx_mounts(self):
        """The throwaway nginx must see exactly what the compose service sees."""
        nginx = _compose()["services"]["nginx"]
        block = _validator_block(self.script)
        self.assertIn(f"{nginx['image']} nginx -t </dev/null", block)
        config_mounts = [v for v in nginx["volumes"] if v.startswith("./config/")]
        self.assertGreaterEqual(len(config_mounts), 5)
        for vol in config_mounts:
            src, target = vol.split(":")[:2]
            self.assertIn(f"/{src[2:]}:{target}:ro", block, vol)

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

    def test_compose_run_never_reads_the_script_from_stdin(self):
        """The script is ssh's stdin; an interactive `compose run` would eat
        the rest of it and the deploy would silently stop there."""
        script = self.script.replace("\\\n", " ")
        runs = [
            line.strip()
            for line in script.splitlines()
            if "docker compose" in line and (" run " in line or " exec " in line)
            and not line.strip().startswith("#")
        ]
        # exec too: compose exec attaches stdin even with -T; the readiness
        # loop's exec ate the rest of the script and every later step
        # (nginx recreate, chmod, migrate) silently never ran (24.11.2026)
        self.assertGreaterEqual(len(runs), 6)
        for line in runs:
            self.assertIn(" -T ", line)
            self.assertIn("</dev/null", line)


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


class DeployDowntimeTests(SimpleTestCase):
    """Every deploy used to 502 the site from `stop web` (before fetch, nginx
    check, image build) until gunicorn answered. Only what needs web stopped
    may sit between `stop web` and `up -d web`."""

    def setUp(self):
        self.script = _deploy_script()
        self.stop = self.script.index(STOP_WEB)
        self.start = self.script.index("docker compose -f docker-compose.prod.yml up -d web\n")

    def _before_stop(self, needle):
        pos = self.script.index(needle)
        self.assertLess(pos, self.stop, needle)
        return pos

    def _in_window(self, needle):
        pos = self.script.index(needle)
        self.assertGreater(pos, self.stop, needle)
        self.assertLess(pos, self.start, needle)
        return pos

    def test_one_stop_web(self):
        self.assertEqual(self.script.count("docker-compose.prod.yml stop web"), 1)

    def test_fetch_validate_build_happen_before_stop(self):
        self._before_stop("git fetch origin")
        self._before_stop('git archive -o "$WORK_DIR/next.tar" "$NEW_HEAD"')
        self._before_stop(PRE_VALIDATE)
        self.assertIn("docker run --rm \\\n", _validator_block(self.script))
        build = self._before_stop(
            'docker compose -f docker-compose.prod.yml -f "$WORK_DIR/build-override.yml" build web tiktok-daily </dev/null'
        )
        # built from the export of the incoming commit, not the old worktree
        self.assertIn('"$NEXT_DIR" "$NEXT_DIR" > "$WORK_DIR/build-override.yml"', self.script[:build])
        self._before_stop('LC_ALL=C comm -23 "$WORK_DIR/next.txt" "$WORK_DIR/tracked.txt"')

    def test_only_db_and_pull_inside_the_window(self):
        checkpoint = self._in_window("PRAGMA wal_checkpoint(TRUNCATE)")
        backup = self._in_window("/app/backups/db.sqlite3.pre_deploy_${TS}")
        blockers = self._in_window('done < "$WORK_DIR/blockers.txt"')
        pull = self._in_window("git pull origin main")
        restore = self._in_window("/app/db.sqlite3 && rm -f /app/db.sqlite3-wal")
        self.assertLess(checkpoint, backup)
        self.assertLess(backup, blockers)
        self.assertLess(blockers, pull)
        self.assertLess(pull, restore)
        # no per-file git call left in the window
        self.assertNotIn("--error-unmatch", self.script)
        self.assertNotIn("git fetch", self.script[self.stop : self.start])

    def test_pull_never_touches_the_db(self):
        window = self.script[self.stop : self.start]
        self.assertIn("db.sqlite3|db.sqlite3-wal|db.sqlite3-shm) continue ;;", window)
        self.assertIn("git clean -fd -- scripts", window)
        self.assertNotIn("git clean -fd\n", window)
        self.assertNotIn("reset --hard", self.script)

    def test_restore_is_atomic_and_only_after_full_checkpoint(self):
        self.assertIn("mv -f /app/.db_restore_tmp /app/db.sqlite3", self.script)
        snapshot = self.script.index("/tmp/mrcarpet_db_live_${TS}.sqlite3 && chmod 644")
        guard = self.script.rindex('if [ "$CHECKPOINT_OK" = "1" ]; then', 0, snapshot)
        self.assertNotIn("\n          fi\n", self.script[guard:snapshot])

    def test_db_writing_daemons_stop_with_web_and_restart_after(self):
        stop_daemons = self.script.index("for svc in ga4-weekly content-scheduler rozetka-poller; do")
        self.assertLess(stop_daemons, self.stop)
        self.assertGreater(stop_daemons, self.script.index("LC_ALL=C comm -23"))
        self.assertLess(self.script.index("wait || true"), self.script.index("PRAGMA wal_checkpoint"))
        daemons_up = self.script.index("up -d ga4-weekly content-scheduler rozetka-poller\n")
        self.assertGreater(daemons_up, self.start)
        self.assertLess(daemons_up, self.script.index("Waiting until gunicorn answers"))
        restart = self.script.index("restart rozetka-poller </dev/null")
        self.assertGreater(restart, self.script.index("python manage.py migrate --noinput"))

    def test_failure_inside_window_brings_web_back(self):
        trap = self.script.index("trap on_exit EXIT")
        self.assertLess(trap, self.stop)
        self.assertLess(self.script.index("WEB_STOPPED=1"), self.stop)
        self.assertEqual(self.script[self.start :].split("\n")[1].strip(), "WEB_STARTED=1")
        handler = self.script[self.script.index("on_exit() {") : trap]
        self.assertIn('if [ "$WEB_STOPPED" = "1" ] && [ "$WEB_STARTED" = "0" ]; then', handler)
        self.assertIn("up -d web ga4-weekly content-scheduler rozetka-poller </dev/null", handler)

    def test_one_deploy_at_a_time(self):
        wf = yaml.safe_load(_read(".github/workflows/deploy.yml"))
        self.assertEqual(wf["concurrency"]["group"], "deploy-production")
        self.assertIs(wf["concurrency"]["cancel-in-progress"], False)

    def test_only_images_are_pruned(self):
        commands = [l.strip() for l in self.script.splitlines() if not l.strip().startswith("#")]
        self.assertFalse([c for c in commands if "system prune" in c])
        self.assertIn("docker image prune -f", commands)

    def test_containers_stop_fast(self):
        """PID 1 ignores SIGTERM without a handler: every stop sat out 10 s."""
        services = _compose()["services"]
        self.assertIn("&& exec gunicorn core.wsgi:application", services["web"]["command"])
        for name in ("ga4-weekly", "content-scheduler", "rozetka-poller", "tiktok-daily"):
            self.assertIs(services[name].get("init"), True, name)


class MaintenancePageTests(SimpleTestCase):
    """While web is down nginx answers 503 + Retry-After with a static page."""

    def setUp(self):
        self.site = _read("config/mrcarpet.docker")
        self.https = self.site[self.site.index("server_name mrcarpet24.com;") :]

    def _location(self, head):
        start = self.https.index(head)
        return self.https[start : self.https.index("\n    }", start)]

    def test_proxy_errors_become_503_page(self):
        block = self._location("location / {")
        self.assertIn("error_page 502 504 =503 /maintenance.html;", block)
        self.assertNotIn("proxy_intercept_errors on", self.site)
        self.assertIn("proxy_connect_timeout 10;", block)

    def test_static_and_media_unaffected(self):
        for head in ("location ^~ /static/source/pages/ {", "location /static/ {", "location /media/ {"):
            self.assertNotIn("error_page", self._location(head), head)
        self.assertEqual(self.site.count("error_page"), 1)

    def test_retry_after_only_on_the_maintenance_location(self):
        block = self._location("location = /maintenance.html {")
        self.assertIn("internal;", block)
        self.assertIn("add_header Retry-After 60 always;", block)
        self.assertIn('add_header Cache-Control "no-store" always;', block)
        self.assertEqual(self.site.count("add_header Retry-After"), 1)

    def test_page_is_mounted_into_nginx(self):
        block = self._location("location = /maintenance.html {")
        root = re.search(r"root (\S+);", block).group(1)
        volumes = _compose()["services"]["nginx"]["volumes"]
        self.assertIn(f"./config/maintenance:{root}:ro", volumes)
        page = ROOT / "config/maintenance/maintenance.html"
        self.assertTrue(page.is_file())
        html = page.read_text(encoding="utf-8")
        self.assertIn("Сайт оновлюється, зайдіть за хвилину", html)
        self.assertIn('<html lang="uk">', html)
        self.assertNotIn("—", html)
        # self-contained: nothing that needs web or /static
        self.assertNotRegex(html, r'(src|href)="(/|http)')


class DeployExitStatusTests(SimpleTestCase):
    def test_finished_deploy_exits_zero_despite_bash_logout(self):
        text = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        self.assertIn('if [ "$DEPLOY_DONE" = "1" ]; then rc=0; fi', text)
        self.assertIn("DEPLOY_DONE=1\n        echo \"Deployment completed successfully!\"\n        exit 0", text)
