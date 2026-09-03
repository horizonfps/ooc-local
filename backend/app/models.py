"""GGUF profile catalog and downloader for the local model roles."""

import argparse
from pathlib import Path

import httpx

from app.config import CONFIG_DIR, Config, ProfileModel, load_config

CHUNK_BYTES = 1 << 20

DEFAULT_PROFILES: dict[str, dict[str, ProfileModel]] = {
    "recommended": {
        "narrator": ProfileModel(
            hf_repo="TheDrummer/Rocinante-12B-v1.1-GGUF",
            file="Rocinante-12B-v1.1-Q4_K_M.gguf",
            port=5101, ctx=24576, gpu_layers=-1),
        "utility": ProfileModel(
            hf_repo="lmstudio-community/Qwen3.5-4B-GGUF",
            file="Qwen3.5-4B-Q4_K_M.gguf",
            port=5102, ctx=8192, gpu_layers=-1),
    },
    "premium": {
        "narrator": ProfileModel(
            hf_repo="bartowski/TheDrummer_Cydonia-24B-v4.3-GGUF",
            file="TheDrummer_Cydonia-24B-v4.3-Q4_K_M.gguf",
            port=5101, ctx=24576, gpu_layers=-1),
        "utility": ProfileModel(
            hf_repo="unsloth/Qwen3.5-4B-GGUF",
            file="Qwen3.5-4B-Q8_0.gguf",
            port=5102, ctx=8192, gpu_layers=-1),
    },
}


class UnknownProfile(Exception):
    pass


def models_dir() -> Path:
    return CONFIG_DIR / "models"


def resolve_profile(name: str, config: Config) -> dict[str, ProfileModel]:
    if name in config.profiles:
        return config.profiles[name]
    if name in DEFAULT_PROFILES:
        return DEFAULT_PROFILES[name]
    raise UnknownProfile(name)


def download_one(model: ProfileModel, dest_dir: Path, client: httpx.Client) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    local = dest_dir / model.file
    have = local.stat().st_size if local.exists() else 0
    url = f"https://huggingface.co/{model.hf_repo}/resolve/main/{model.file}"
    headers = {"Range": f"bytes={have}-"} if have > 0 else {}

    with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 416:
            return "skipped"

        if response.status_code == 206:
            total = _range_total(response.headers.get("Content-Range"))
            if total is not None and total == have:
                return "skipped"
            mode = "ab"
            outcome = "resumed"
        else:
            response.raise_for_status()
            total = _content_length(response.headers.get("Content-Length"))
            mode = "wb"
            outcome = "downloaded"
            have = 0

        with local.open(mode) as f:
            for chunk in response.iter_bytes(CHUNK_BYTES):
                f.write(chunk)

    final_size = local.stat().st_size
    if total is not None and final_size != total:
        return "partial"
    return outcome


def _content_length(value: str | None) -> int | None:
    return int(value) if value is not None else None


def _range_total(value: str | None) -> int | None:
    if value is None:
        return None
    total = value.rsplit("/", 1)[-1]
    return int(total) if total != "*" else None


def download_profile(name: str, config: Config, roles: list[str] | None = None) -> dict[str, str]:
    profile = resolve_profile(name, config)
    items = {role: model for role, model in profile.items() if roles is None or role in roles}

    total_bytes = 0
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(None, connect=30.0)) as client:
        sizes: dict[str, int | None] = {}
        for role, model in items.items():
            url = f"https://huggingface.co/{model.hf_repo}/resolve/main/{model.file}"
            head = client.head(url)
            size = _content_length(head.headers.get("Content-Length"))
            sizes[role] = size
            if size is not None:
                total_bytes += size
            print(f"{role} {model.hf_repo} {model.file} {_format_gb(size)}")

        print(f"total {_format_gb(total_bytes)}")

        results: dict[str, str] = {}
        for role, model in items.items():
            result = download_one(model, models_dir(), client)
            results[role] = result
            print(f"{role} {result}")

    return results


def _format_gb(size: int | None) -> str:
    if size is None:
        return "? GB"
    return f"{size / (1 << 30):.2f} GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.models")
    sub = parser.add_subparsers(dest="command", required=True)

    download = sub.add_parser("download", help="Download the GGUF weights for a model profile")
    download.add_argument(
        "--profile", required=True,
        help="Profile name (built-in: recommended = 12 GB VRAM, premium = 16 GB+ VRAM)")
    download.add_argument("--role", action="append", help="Limit download to this role (repeatable)")

    args = parser.parse_args(argv)

    config = load_config()

    if args.command == "download":
        try:
            resolve_profile(args.profile, config)
        except UnknownProfile:
            print(f"unknown profile: {args.profile}")
            return 2

        results = download_profile(args.profile, config, roles=args.role)
        if any(result == "partial" for result in results.values()):
            return 1
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
