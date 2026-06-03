from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLE_PAGES = [
    PROJECT_ROOT / "static" / "help.html",
    PROJECT_ROOT / "static" / "admin.html",
    PROJECT_ROOT / "templates" / "index.html",
    PROJECT_ROOT / "templates" / "escalations.html",
]
MAIN_LANDMARK_PAGES = [
    PROJECT_ROOT / "static" / "chat.html",
    PROJECT_ROOT / "static" / "help.html",
    PROJECT_ROOT / "static" / "metrics.html",
    PROJECT_ROOT / "static" / "widget.html",
    PROJECT_ROOT / "templates" / "index.html",
    PROJECT_ROOT / "templates" / "ask_result.html",
    PROJECT_ROOT / "templates" / "escalations.html",
]
STATIC_A11Y_PATHS = [
    "/static/chat.html",
    "/static/help.html",
    "/static/admin.html",
    "/static/metrics.html",
    "/static/agent.html",
    "/static/analytics.html",
    "/static/login.html",
    "/static/widget.html",
]
TEMPLATE_A11Y_CONTEXTS = {
    "index.html": {
        "inbox_stats": {"total": 3},
        "traces": [
            {
                "trace_id": "trace-001",
                "started_at": "2026-04-21T08:00:00Z",
                "final_route": "auto",
                "final_quality": 88,
                "final_relevance": 91,
            }
        ],
    },
    "ask_result.html": {
        "question": "Как вернуть товар?",
        "response": {
            "answer": "Возврат доступен в течение 14 дней.",
            "route": "auto",
            "quality": 90,
            "relevance": 93,
            "trace_id": "trace-001",
        },
    },
    "escalations.html": {
        "total": 1,
        "items": [
            {
                "ts": "2026-04-21T08:00:00Z",
                "entity_id": "ORD-1",
                "question": "Где мой заказ?",
                "answer": "Передано оператору",
                "route": "human",
                "quality": 45,
                "relevance": 55,
            }
        ],
    },
}
TEMPLATE_A11Y_PATHS = [f"/{name}" for name in TEMPLATE_A11Y_CONTEXTS]
ALL_A11Y_PATHS = STATIC_A11Y_PATHS + TEMPLATE_A11Y_PATHS
REMOVED_TRACE_UI_TEMPLATES = {"traces.html", "trace_detail.html"}
AXE_SUBPROCESS_TIMEOUT_SEC = 180
AXE_PYTEST_TIMEOUT_SEC = AXE_SUBPROCESS_TIMEOUT_SEC + 60


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


@pytest.fixture(scope="module")
def rendered_a11y_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_root = tmp_path_factory.mktemp("a11y-site")
    shutil.copytree(PROJECT_ROOT / "static", output_root / "static")

    env = Environment(loader=FileSystemLoader(str(PROJECT_ROOT / "templates")))
    for template_name, context in TEMPLATE_A11Y_CONTEXTS.items():
        rendered = env.get_template(template_name).render(**context)
        (output_root / template_name).write_text(rendered, encoding="utf-8")

    return output_root


@pytest.fixture(scope="module")
def a11y_base_url(rendered_a11y_site: Path) -> str:
    handler = partial(_QuietStaticHandler, directory=str(rendered_a11y_site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()


def test_all_table_headers_define_scope() -> None:
    missing: dict[str, int] = {}

    for path in TABLE_PAGES:
        html = path.read_text(encoding="utf-8")
        th_without_scope = [
            match.group(0)
            for match in re.finditer(r"<th\b(?![^>]*\bscope=)[^>]*>", html)
        ]
        if th_without_scope:
            missing[path.name] = len(th_without_scope)

    assert not missing, f"Headers without scope: {missing}"


def test_chat_upload_dropzone_is_keyboard_accessible() -> None:
    html = (PROJECT_ROOT / "static" / "chat.html").read_text(encoding="utf-8")

    assert 'id="uploadDropzone"' in html
    assert 'role="button"' in html
    assert 'tabindex="0"' in html
    assert 'aria-label="Загрузить документы"' in html


def test_components_css_defines_focus_visible_styles() -> None:
    css = (PROJECT_ROOT / "static" / "styles" / "components.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "outline" in css


@pytest.mark.parametrize("path", MAIN_LANDMARK_PAGES)
def test_pages_define_one_main_landmark(path: Path) -> None:
    html = path.read_text(encoding="utf-8")

    assert len(re.findall(r"<main\b", html)) == 1
    assert len(re.findall(r"</main>", html)) == 1


def test_admin_related_link_is_inside_landmark() -> None:
    html = (PROJECT_ROOT / "static" / "admin.html").read_text(encoding="utf-8")

    assert '<nav style="padding: 0 32px;" aria-label="Admin related pages">' in html


def test_widget_page_is_covered_by_a11y_landmark_checks() -> None:
    widget_path = PROJECT_ROOT / "static" / "widget.html"

    assert widget_path in MAIN_LANDMARK_PAGES
    assert "/static/widget.html" in STATIC_A11Y_PATHS


def test_removed_trace_ui_templates_are_not_a11y_targets() -> None:
    table_page_names = {path.name for path in TABLE_PAGES}
    landmark_page_names = {path.name for path in MAIN_LANDMARK_PAGES}

    assert REMOVED_TRACE_UI_TEMPLATES.isdisjoint(table_page_names)
    assert REMOVED_TRACE_UI_TEMPLATES.isdisjoint(landmark_page_names)
    assert REMOVED_TRACE_UI_TEMPLATES.isdisjoint(TEMPLATE_A11Y_CONTEXTS)
    assert not any(path.endswith("/traces.html") for path in ALL_A11Y_PATHS)
    assert not any(path.endswith("/trace_detail.html") for path in ALL_A11Y_PATHS)


def test_chat_main_landmark_wraps_primary_chat_shell() -> None:
    html = (PROJECT_ROOT / "static" / "chat.html").read_text(encoding="utf-8")
    main_start = html.index('<main class="main-pane">')
    main_end = html.index("</main>", main_start)

    assert main_start < html.index('id="chatContainer"') < main_end
    assert main_start < html.index('id="chatForm"') < main_end


@pytest.mark.parametrize("template_name", TEMPLATE_A11Y_CONTEXTS)
def test_a11y_templates_render_for_snapshot(template_name: str) -> None:
    env = Environment(loader=FileSystemLoader(str(PROJECT_ROOT / "templates")))

    rendered = env.get_template(template_name).render(**TEMPLATE_A11Y_CONTEXTS[template_name])

    assert "<html" in rendered


@pytest.mark.parametrize("template_name", TEMPLATE_A11Y_CONTEXTS)
def test_a11y_template_heading_order_is_sequential(template_name: str) -> None:
    env = Environment(loader=FileSystemLoader(str(PROJECT_ROOT / "templates")))
    rendered = env.get_template(template_name).render(**TEMPLATE_A11Y_CONTEXTS[template_name])
    levels = [int(match.group(1)) for match in re.finditer(r"<h([1-6])\b", rendered)]

    for previous, current in zip(levels, levels[1:], strict=False):
        assert current <= previous + 1, f"{template_name}: h{previous} skips to h{current}"


def _axe_cli_available() -> bool:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        return False
    try:
        probe = subprocess.run(
            [npx, "--no-install", "@axe-core/cli", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return probe.returncode == 0


def _axe_chrome_startup_failed(completed: subprocess.CompletedProcess[str]) -> bool:
    output = f"{completed.stderr}\n{completed.stdout}".lower()
    return "sessionnotcreatederror" in output and "chrome not reachable" in output


@pytest.mark.skipif(
    not _axe_cli_available(),
    reason="@axe-core/cli not installed (npm i -g @axe-core/cli) — running headless axe scan unavailable",
)
@pytest.mark.timeout(AXE_PYTEST_TIMEOUT_SEC)
@pytest.mark.parametrize("page_path", ALL_A11Y_PATHS)
def test_axe_has_no_serious_or_critical_findings(
    a11y_base_url: str,
    page_path: str,
    tmp_path: Path,
) -> None:
    report_name = f"{Path(page_path).name}.json"
    report_path = tmp_path / report_name
    command = [
        shutil.which("npx.cmd") or shutil.which("npx") or "npx",
        "--no-install",
        "@axe-core/cli",
        f"{a11y_base_url}{page_path}",
        "--save",
        report_name,
        "--timeout",
        "120",
        "--load-delay",
        "1000",
        "--no-reporter",
        "--chrome-options=--headless=new --disable-gpu --disable-dev-shm-usage --no-sandbox",
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    completed = None
    for attempt in range(2):
        try:
            completed = subprocess.run(
                command,
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=AXE_SUBPROCESS_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(
                f"axe-cli timed out after {AXE_SUBPROCESS_TIMEOUT_SEC}s for {page_path}: {exc}"
            )
        if completed.returncode == 0 or attempt == 1 or not _axe_chrome_startup_failed(completed):
            break

    assert completed is not None
    assert completed.returncode == 0, completed.stderr or completed.stdout

    data = json.loads(report_path.read_text(encoding="utf-8"))[0]
    blocking = []
    for section_name in ("violations", "incomplete"):
        for finding in data.get(section_name, []):
            if finding.get("impact") in {"critical", "serious"}:
                blocking.append(f"{section_name}:{finding['id']}:{finding['impact']}")

    assert not blocking, f"{page_path} blocking axe findings: {', '.join(blocking)}"
