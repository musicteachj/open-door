"""The API serves the built web app: assets, deep links, and the per-response index.html."""

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security_headers import content_security_policy
from app.main import create_app
from app.web_app import load_index
from tests.conftest import TEST_KEYRING, UNREACHABLE_DATABASE_URL

INDEX = """<!doctype html>
<html lang="en"><head>
<meta charset="UTF-8" />
<meta name="csp-nonce" content="" />
<meta name="turnstile-site-key" content="" />
<title>Open Door</title>
</head><body><div id="root"></div><script type="module" src="/assets/app-abc123.js"></script>
</body></html>
"""
SITE_KEY = "0x4AAAA-site&key"
NONCE_META = re.compile(r'<meta name="csp-nonce" content="([^"]*)"')


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX)
    (root / "assets" / "app-abc123.js").write_text("console.log(1)")
    (root / "assets" / "style-abc123.css").write_text("body{}")
    (root / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside the dist")
    return root


def client_for(dist_dir: Path | None, **overrides: object) -> TestClient:
    fields: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": UNREACHABLE_DATABASE_URL,
        "app_origin": "http://localhost:5173",
        "encryption_keyring_file": None,
        "encryption_keyring": TEST_KEYRING,
        "web_dist_dir": dist_dir,
        "turnstile_site_key": SITE_KEY,
        # Outside production the two keys are set together or not at all.
        "turnstile_secret_key": "1x0000000000000000000000000000000AA",
    }
    blank_site_key = overrides.get("turnstile_site_key") == ""
    if blank_site_key:
        fields["turnstile_secret_key"] = None
    fields.update(overrides)
    settings = Settings(**fields)  # type: ignore[arg-type]
    if blank_site_key:
        # Outside production Settings turns a blank key into the test key; the page server
        # itself still writes whatever it is given.
        settings = settings.model_copy(update={"turnstile_site_key": ""})
    return TestClient(create_app(settings))


def test_an_asset_is_served_immutable_with_its_type(dist: Path) -> None:
    with client_for(dist) as client:
        js = client.get("/assets/app-abc123.js")
        css = client.get("/assets/style-abc123.css")
    assert js.status_code == 200
    assert js.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "javascript" in js.headers["content-type"]
    assert css.headers["content-type"].startswith("text/css")
    assert css.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_a_missing_asset_is_404_never_index_html(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.get("/assets/gone-123.js")
    assert response.status_code == 404
    assert "csp-nonce" not in response.text
    assert "immutable" not in response.headers.get("cache-control", "")


@pytest.mark.parametrize("path", ["/", "/ask", "/directory/abc", "/index.html"])
def test_pages_get_index_html_uncached(dist: Path, path: str) -> None:
    with client_for(dist) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert '<div id="root">' in response.text


def test_head_works_for_a_page(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.head("/ask")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_unknown_api_paths_stay_json_404s(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.get("/api/v1/nope")
        bare = client.get("/api/nope")
    for r in (response, bare):
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.headers["cache-control"] == "no-store"


def test_each_page_has_a_fresh_nonce_in_the_header_and_the_meta_tag(dist: Path) -> None:
    with client_for(dist) as client:
        first = client.get("/")
        second = client.get("/ask")
    nonces = []
    for response in (first, second):
        match = NONCE_META.search(response.text)
        assert match is not None
        nonce = match.group(1)
        assert len(nonce) >= 16
        assert response.headers["content-security-policy"] == content_security_policy(nonce)
        nonces.append(nonce)
    assert nonces[0] != nonces[1]


def test_the_site_key_is_written_escaped_into_its_meta_tag(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.get("/")
    assert '<meta name="turnstile-site-key" content="0x4AAAA-site&amp;key" />' in response.text


def test_an_unset_site_key_leaves_the_tag_empty(dist: Path) -> None:
    with client_for(dist, turnstile_site_key="") as client:
        response = client.get("/")
    assert '<meta name="turnstile-site-key" content="" />' in response.text


def test_only_pages_carry_the_csp(dist: Path) -> None:
    with client_for(dist) as client:
        asset = client.get("/assets/app-abc123.js")
        api = client.get("/api/v1/nope")
        page = client.get("/")
    assert "content-security-policy" not in asset.headers
    assert "content-security-policy" not in api.headers
    assert "content-security-policy" in page.headers


def test_every_response_has_the_security_headers(dist: Path) -> None:
    with client_for(dist) as client:
        responses = [
            client.get("/"),
            client.get("/assets/app-abc123.js"),
            client.get("/assets/gone.js"),
            client.get("/favicon.svg"),
        ]
        responses.append(client.head("/ask"))
    for response in responses:
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["strict-transport-security"] == (
            "max-age=31536000; includeSubDomains"
        )
        assert response.headers["referrer-policy"] == "same-origin"
        assert response.headers["permissions-policy"] == (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        assert response.headers["cross-origin-opener-policy"] == "same-origin"


def test_a_file_in_the_dist_root_is_served_with_a_short_cache(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.text == "<svg/>"
    assert response.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.parametrize(
    "path",
    [
        "/assets/../index.html",
        "/assets/..%2f..%2fsecret.txt",
        "/assets/%2e%2e/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/%2e%2e/secret.txt",
        "/%2e%2e%2fsecret.txt",
        "/assets/%2e%2e%2f%2e%2e%2fapp/main.py",
        "/....//secret.txt",
        "/%00",
    ],
)
def test_traversal_never_leaks_a_file_outside_the_dist(dist: Path, path: str) -> None:
    with client_for(dist) as client:
        response = client.get(path)
    assert "outside the dist" not in response.text
    assert "def create_app" not in response.text
    # What the client sends may be normalized to a page; it is never a file from outside.
    assert response.status_code in (200, 400, 404)
    if response.status_code == 200:
        assert response.headers["content-type"].startswith("text/html")


def test_a_symlink_out_of_the_dist_is_not_served(dist: Path, tmp_path: Path) -> None:
    (dist / "link.txt").symlink_to(tmp_path / "secret.txt")
    with client_for(dist) as client:
        response = client.get("/link.txt")
    assert "outside the dist" not in response.text
    # Not a file the app serves, so it is a deep link and gets the page.
    assert response.headers["content-type"].startswith("text/html")


def test_the_raw_index_file_is_never_served_unrendered(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.get("/index.html")
    assert NONCE_META.search(response.text).group(1) != ""  # type: ignore[union-attr]


def test_post_to_a_page_path_is_a_json_404_not_the_page(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.post("/ask", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_write_to_an_unknown_api_path_stays_a_json_404(dist: Path, method: str) -> None:
    # The page server is the router's fallback, not a GET route, so it never turns an unknown API
    # path into a 405.
    with client_for(dist) as client:
        response = client.request(
            method, "/api/v1/nope", headers={"Origin": "http://localhost:5173"}
        )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_wrong_method_on_a_real_api_route_is_still_405(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.delete("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 405


def test_bare_api_is_a_json_404_not_the_page(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.get("/api")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_missing_asset_is_never_cached(dist: Path) -> None:
    with client_for(dist) as client:
        response = client.get("/assets/app-def456.js")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/.vite/manifest.json", "/.gitkeep", "/assets/.hidden.js"])
def test_hidden_files_in_the_dist_are_never_served(dist: Path, path: str) -> None:
    (dist / ".vite").mkdir()
    (dist / ".vite" / "manifest.json").write_text("the manifest")
    (dist / ".gitkeep").write_text("the keep file")
    (dist / "assets" / ".hidden.js").write_text("the hidden asset")
    with client_for(dist) as client:
        response = client.get(path)
    assert response.status_code == 404
    assert "the " not in response.text


def test_with_no_dist_nothing_is_served_and_no_csp_is_sent() -> None:
    with client_for(None) as client:
        root = client.get("/")
        asset = client.get("/assets/app.js")
        deep = client.get("/ask")
        api = client.get("/api/v1/nope")
    for response in (root, asset, deep):
        assert response.status_code == 404
        assert "content-security-policy" not in response.headers
    assert "content-security-policy" not in api.headers


@pytest.mark.parametrize("missing", ["csp-nonce", "turnstile-site-key"])
def test_it_refuses_to_start_when_a_placeholder_is_missing(dist: Path, missing: str) -> None:
    html = INDEX.replace(f'<meta name="{missing}" content="" />', "")
    (dist / "index.html").write_text(html)
    with pytest.raises(ValueError, match=missing):
        client_for(dist)


def test_it_refuses_to_start_without_an_assets_folder(dist: Path) -> None:
    for asset in (dist / "assets").iterdir():
        asset.unlink()
    (dist / "assets").rmdir()
    with pytest.raises(ValueError, match="assets"):
        client_for(dist)


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_web_dist_dir_means_unset(blank: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=UNREACHABLE_DATABASE_URL,
        web_dist_dir=blank,
    )
    assert settings.web_dist_dir is None


def test_it_refuses_to_start_without_an_index_file(dist: Path) -> None:
    (dist / "index.html").unlink()
    with pytest.raises(ValueError, match=r"index\.html"):
        client_for(dist)


def test_load_index_returns_the_text(dist: Path) -> None:
    assert "csp-nonce" in load_index(dist)


# The walkthrough's video (Phase 8, Task 44). Safari plays a video only from a server that
# answers range requests, so the page server's file responses must keep doing so.
VIDEO = bytes(range(256)) * 4  # 1,024 bytes, each position distinct


@pytest.fixture
def media(dist: Path) -> Path:
    (dist / "media").mkdir()
    (dist / "media" / "walkthrough.mp4").write_bytes(VIDEO)
    return dist


def test_the_video_says_it_accepts_ranges(media: Path) -> None:
    with client_for(media) as client:
        response = client.get("/media/walkthrough.mp4")
    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"
    # Asked again each visit (a 304 while unchanged), so a re-recorded video never shows beside the
    # transcript of the one before, which ships in the page's own hashed code.
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"]
    assert response.content == VIDEO


def test_an_unchanged_video_is_not_sent_again(media: Path) -> None:
    with client_for(media) as client:
        etag = client.get("/media/walkthrough.mp4").headers["etag"]
        response = client.get("/media/walkthrough.mp4", headers={"If-None-Match": etag})
    assert response.status_code == 304


def test_a_range_request_gets_206_and_only_those_bytes(media: Path) -> None:
    with client_for(media) as client:
        response = client.get("/media/walkthrough.mp4", headers={"Range": "bytes=100-199"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 100-199/{len(VIDEO)}"
    assert response.content == VIDEO[100:200]
    assert response.headers["cache-control"] == "no-cache"


def test_an_open_ended_range_gets_the_rest_of_the_file(media: Path) -> None:
    # What Safari and Chromium send first: `bytes=0-`, then later pieces.
    with client_for(media) as client:
        response = client.get("/media/walkthrough.mp4", headers={"Range": "bytes=1000-"})
    assert response.status_code == 206
    assert response.content == VIDEO[1000:]


def test_a_range_past_the_end_is_416(media: Path) -> None:
    with client_for(media) as client:
        response = client.get("/media/walkthrough.mp4", headers={"Range": "bytes=5000-6000"})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(VIDEO)}"


@pytest.mark.parametrize("path", ["/media/gone.mp4", "/media/", "/media/sub/walkthrough.jpg"])
def test_a_missing_media_file_is_a_404_never_the_page(media: Path, path: str) -> None:
    # A video element given the HTML page fails silently; a 404 shows in the network panel.
    with client_for(media) as client:
        response = client.get(path)
    assert response.status_code == 404
    assert "csp-nonce" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("path", "status"),
    [("/" + "a" * 300, 200), ("/media/" + "a" * 300, 404), ("/" + "a/" * 3000, 200)],
    ids=["a long name", "a long media name", "a long path"],
)
def test_a_name_too_long_for_the_file_system_is_no_file_not_a_500(
    media: Path, path: str, status: int
) -> None:
    """The phase's security review: a segment over 255 bytes made `is_file()` raise, so anyone
    could get a 500 and a logged traceback."""
    with client_for(media) as client:
        response = client.get(path)
    assert response.status_code == status


def test_a_file_that_goes_while_it_is_looked_up_is_no_file_not_a_500(
    media: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recording installed again, or a deploy, can replace a file between the lookup's steps."""
    real_stat = Path.stat
    looked: list[Path] = []

    def gone(self: Path, *args: Any, **kwargs: Any) -> Any:
        # There for the first look, gone from the next on.
        if self.name == "walkthrough.mp4":
            looked.append(self)
            if len(looked) > 1:
                raise FileNotFoundError(self)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", gone)
    with client_for(media) as client:
        response = client.get("/media/walkthrough.mp4")
    # Served from the one look the lookup takes, or no file: never a 500 (a separate check and
    # stat gave one when the file went between them).
    assert response.status_code in (200, 404)


def test_a_page_path_that_only_starts_like_media_is_still_the_page(media: Path) -> None:
    with client_for(media) as client:
        response = client.get("/mediation")
    assert response.status_code == 200
    assert "csp-nonce" in response.text


def test_the_page_lets_the_video_load_from_its_own_origin(dist: Path) -> None:
    with client_for(dist) as client:
        csp = client.get("/walkthrough").headers["content-security-policy"]
    assert "media-src 'self'" in csp
