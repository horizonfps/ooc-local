import httpx
import pytest

import app.models as models
from app.config import Config, ProfileModel

NARRATOR_CONTENT = b"narrator-bytes" * 100
UTILITY_CONTENT = b"utility-bytes" * 50


def _config(profiles: dict[str, dict[str, ProfileModel]] | None = None) -> Config:
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "profiles": profiles or {},
        }
    )


def _test_profile() -> dict[str, ProfileModel]:
    return {
        "narrator": ProfileModel(hf_repo="acme/narrator-repo", file="narrator.gguf", port=5101),
        "utility": ProfileModel(hf_repo="acme/utility-repo", file="utility.gguf", port=5102),
    }


def _content_for(request: httpx.Request) -> bytes:
    if "narrator.gguf" in request.url.path:
        return NARRATOR_CONTENT
    if "utility.gguf" in request.url.path:
        return UTILITY_CONTENT
    raise AssertionError(f"unexpected url: {request.url}")


def _basic_handler(request: httpx.Request) -> httpx.Response:
    content = _content_for(request)
    if request.method == "HEAD":
        return httpx.Response(200, headers={"Content-Length": str(len(content))})

    range_header = request.headers.get("range")
    if range_header:
        start = int(range_header.split("=")[1].rstrip("-"))
        if start >= len(content):
            return httpx.Response(416)
        chunk = content[start:]
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {start}-{len(content) - 1}/{len(content)}"},
            content=chunk,
        )
    return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)


@pytest.fixture(autouse=True)
def _isolate_models_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_dir", lambda: tmp_path / "models")
    return tmp_path / "models"


_RealClient = httpx.Client


def _client(handler) -> httpx.Client:
    return _RealClient(transport=httpx.MockTransport(handler))


def test_downloads_both_roles_from_scratch(monkeypatch, tmp_path):
    config = _config({"test": _test_profile()})
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return _basic_handler(request)

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client(handler))
    results = models.download_profile("test", config)

    assert results == {"narrator": "downloaded", "utility": "downloaded"}
    assert (models.models_dir() / "narrator.gguf").read_bytes() == NARRATOR_CONTENT
    assert (models.models_dir() / "utility.gguf").read_bytes() == UTILITY_CONTENT


def test_resumes_partial_download(monkeypatch):
    config = _config({"test": _test_profile()})
    dest = models.models_dir()
    dest.mkdir(parents=True)
    have = NARRATOR_CONTENT[:50]
    (dest / "narrator.gguf").write_bytes(have)

    seen_ranges = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "narrator.gguf" in request.url.path and request.method != "HEAD":
            seen_ranges.append(request.headers.get("range"))
        return _basic_handler(request)

    result = models.download_one(_test_profile()["narrator"], dest, _client(handler))

    assert result == "resumed"
    assert seen_ranges == [f"bytes={len(have)}-"]
    assert (dest / "narrator.gguf").read_bytes() == NARRATOR_CONTENT


def test_complete_file_is_skipped_without_body_get():
    config = _test_profile()["narrator"]
    dest_dir = models.models_dir()
    dest_dir.mkdir(parents=True)
    (dest_dir / "narrator.gguf").write_bytes(NARRATOR_CONTENT)

    body_bytes_read = []

    def handler(request: httpx.Request) -> httpx.Response:
        response = _basic_handler(request)
        if response.status_code == 206:
            body_bytes_read.append(len(response.content))
        return response

    result = models.download_one(config, dest_dir, _client(handler))

    assert result == "skipped"
    assert body_bytes_read == []
    assert (dest_dir / "narrator.gguf").read_bytes() == NARRATOR_CONTENT


def test_server_ignoring_range_rewrites_from_scratch():
    config = _test_profile()["narrator"]
    dest_dir = models.models_dir()
    dest_dir.mkdir(parents=True)
    (dest_dir / "narrator.gguf").write_bytes(b"stale-partial-data")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(NARRATOR_CONTENT))},
            content=NARRATOR_CONTENT,
        )

    result = models.download_one(config, dest_dir, _client(handler))

    assert result == "downloaded"
    assert (dest_dir / "narrator.gguf").read_bytes() == NARRATOR_CONTENT


def test_role_filter_downloads_only_that_role(monkeypatch):
    config = _config({"test": _test_profile()})
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _basic_handler(request)

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client(handler))
    results = models.download_profile("test", config, roles=["utility"])

    assert results == {"utility": "downloaded"}
    assert not (models.models_dir() / "narrator.gguf").exists()
    assert (models.models_dir() / "utility.gguf").read_bytes() == UTILITY_CONTENT
    assert all("narrator" not in path for path in calls)


def test_resolve_profile_user_config_overrides_builtin():
    user_profile = {"narrator": ProfileModel(hf_repo="user/repo", file="user.gguf", port=9999)}
    config = _config({"recommended": user_profile})

    resolved = models.resolve_profile("recommended", config)

    assert resolved["narrator"].hf_repo == "user/repo"
    assert resolved is not models.DEFAULT_PROFILES["recommended"]


def test_resolve_profile_falls_back_to_builtin():
    config = _config()
    resolved = models.resolve_profile("recommended", config)
    assert resolved == models.DEFAULT_PROFILES["recommended"]


def test_resolve_profile_unknown_name_raises():
    config = _config()
    with pytest.raises(models.UnknownProfile):
        models.resolve_profile("ghost", config)


def test_size_mismatch_returns_partial_and_keeps_file():
    config = _test_profile()["narrator"]
    dest_dir = models.models_dir()
    dest_dir.mkdir(parents=True)

    def handler(request: httpx.Request) -> httpx.Response:
        # Advertises a larger size than what is actually sent.
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(NARRATOR_CONTENT) + 100)},
            content=NARRATOR_CONTENT,
        )

    result = models.download_one(config, dest_dir, _client(handler))

    assert result == "partial"
    assert (dest_dir / "narrator.gguf").exists()
    assert (dest_dir / "narrator.gguf").read_bytes() == NARRATOR_CONTENT


def test_main_unknown_profile_exits_2_without_requests(monkeypatch, capsys):
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(404)

    monkeypatch.setattr(models, "load_config", lambda: _config())
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client(handler))

    code = models.main(["download", "--profile", "ghost"])

    assert code == 2
    assert called == []


def test_main_partial_download_exits_1(monkeypatch):
    config = _config({"test": _test_profile()})

    def handler(request: httpx.Request) -> httpx.Response:
        content = _content_for(request)
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": str(len(content) + 1)})
        return httpx.Response(200, headers={"Content-Length": str(len(content) + 1)}, content=content)

    monkeypatch.setattr(models, "load_config", lambda: config)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client(handler))

    code = models.main(["download", "--profile", "test"])

    assert code == 1


def test_default_profiles_have_narrator_and_utility_with_distinct_ports():
    for name in ("recommended", "premium"):
        profile = models.DEFAULT_PROFILES[name]
        assert set(profile.keys()) == {"narrator", "utility"}
        assert profile["narrator"].port != profile["utility"].port


def test_prints_sizes_before_downloading(monkeypatch, capsys):
    config = _config({"test": _test_profile()})

    def handler(request: httpx.Request) -> httpx.Response:
        return _basic_handler(request)

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client(handler))
    models.download_profile("test", config)

    out = capsys.readouterr().out
    narrator_line_index = out.index("acme/narrator-repo")
    downloaded_line_index = out.index("downloaded")
    assert narrator_line_index < downloaded_line_index
