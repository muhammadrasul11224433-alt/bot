from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
import time
import uuid
from pathlib import Path

import imageio_ffmpeg
import yt_dlp

from config import (
    DOWNLOADS_DIR,
    MAX_AUDIO_SECONDS,
    MAX_VIDEO_SECONDS,
    ROUND_SECONDS,
    SEARCH_COUNT,
    TELEGRAM_MAX_FILE,
)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
YT_ID_RE = re.compile(r"(?:v=|/shorts/|youtu\.be/|embed/)([\w-]{11})")

FFMPEG_LOGLEVEL = "error"
AUDIO_EXTS = (".m4a", ".mp3", ".aac", ".ogg")

_locks: dict[str, asyncio.Lock] = {}
_search_cache: dict[str, tuple[float, list[dict]]] = {}
SEARCH_TTL = 60 * 30


def unique_path(suffix: str) -> Path:
    return DOWNLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"


def format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return ""
    sec = int(seconds)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def extract_url(text: str) -> str | None:
    match = URL_RE.search(text or "")
    return match.group(0).rstrip(").,]>\"'") if match else None


def youtube_id(url: str, fallback: str | None = None) -> str:
    if fallback and re.fullmatch(r"[\w-]{11}", fallback):
        return fallback
    found = YT_ID_RE.search(url or "")
    if found:
        return found.group(1)
    return hashlib.md5((url or "x").encode()).hexdigest()[:16]


def cached_file(stem: str, exts: tuple[str, ...]) -> Path | None:
    for ext in exts:
        path = DOWNLOADS_DIR / f"{stem}{ext}"
        if path.exists() and path.stat().st_size > 2000:
            return path
    return None


def _ydl_base(**extra) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 15,
        "concurrent_fragment_downloads": 8,
        "extractor_args": {
            "youtube": {"player_client": ["android", "web", "tv", "ios"]}
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    }
    opts.update(extra)
    return opts


def _search_sync(query: str) -> list[dict]:
    opts = _ydl_base(
        extract_flat="in_playlist",
        skip_download=True,
        ignoreerrors=True,
        playlistend=SEARCH_COUNT,
        ffmpeg_location=None,
    )
    opts.pop("ffmpeg_location", None)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{SEARCH_COUNT}:{query}", download=False)
    entries = (info or {}).get("entries") or []
    results: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry or not entry.get("id"):
            continue
        vid = entry["id"]
        if vid in seen:
            continue
        duration = entry.get("duration")
        if duration and duration > MAX_AUDIO_SECONDS and len(results) >= 3:
            continue
        seen.add(vid)
        results.append(
            {
                "id": vid,
                "title": (entry.get("title") or "Unknown").strip(),
                "url": entry.get("webpage_url")
                or f"https://www.youtube.com/watch?v={vid}",
                "duration": int(duration) if duration else None,
                "uploader": (entry.get("uploader") or entry.get("channel") or "").strip(),
            }
        )
        if len(results) >= SEARCH_COUNT:
            break
    return results[:SEARCH_COUNT]


def _find_downloaded(stem: str) -> Path | None:
    matches = [
        p
        for p in DOWNLOADS_DIR.glob(f"{stem}.*")
        if p.is_file() and p.suffix.lower() not in {".part", ".ytdl", ".tmp"}
    ]
    return max(matches, key=lambda p: p.stat().st_size) if matches else None


def _to_m4a_fast(src: Path, dest: Path) -> Path:
    """Strip video without re-encoding when the audio is already AAC."""
    try:
        _run_ffmpeg_sync(
            [
                "-y",
                "-i",
                str(src),
                "-vn",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(dest),
            ]
        )
        if dest.exists() and dest.stat().st_size > 1000:
            return dest
    except RuntimeError:
        pass
    _run_ffmpeg_sync(
        [
            "-y",
            "-i",
            str(src),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    return dest


def _download_audio_sync(url: str, video_id: str | None = None) -> Path:
    vid = youtube_id(url, video_id)
    cached = cached_file(vid, AUDIO_EXTS)
    if cached:
        return cached

    outtmpl = str(DOWNLOADS_DIR / f"{vid}.%(ext)s")
    opts = _ydl_base(
        format=(
            "140/bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/"
            "18/best[ext=mp4]/best"
        ),
        outtmpl=outtmpl,
        ffmpeg_location=FFMPEG,
    )
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        duration = (info or {}).get("duration") or 0
        if duration and duration > MAX_AUDIO_SECONDS:
            raise ValueError("too_long")

    path = _find_downloaded(vid)
    if not path or not path.exists():
        raise FileNotFoundError("audio_not_found")

    has_video = path.suffix.lower() in (".mp4", ".mkv", ".webm")
    if has_video or path.suffix.lower() not in AUDIO_EXTS:
        converted = DOWNLOADS_DIR / f"{vid}.m4a"
        if converted != path:
            _to_m4a_fast(path, converted)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            path = converted

    if path.stat().st_size > TELEGRAM_MAX_FILE:
        raise ValueError("too_big")
    return path


def music_query_from_info(info: dict | None) -> str:
    info = info or {}
    track = (info.get("track") or "").strip()
    artist = (info.get("artist") or info.get("creator") or "").strip()
    if track:
        return f"{artist} {track}".strip()
    title = (info.get("title") or "").strip()
    if title and not re.match(r"^video by\b", title, re.IGNORECASE):
        return title
    desc = (info.get("description") or "").strip()
    if desc:
        first = desc.splitlines()[0]
        cleaned = re.sub(r"#\S+", "", first).strip()
        if len(cleaned) >= 3:
            return cleaned[:120]
    return title


def _download_video_sync(
    url: str, max_seconds: int = MAX_VIDEO_SECONDS
) -> tuple[Path, str, str]:
    vid = youtube_id(url)
    cached = cached_file(vid, (".mp4",))
    if cached and cached.stat().st_size <= TELEGRAM_MAX_FILE:
        return cached, "Video", ""

    outtmpl = str(DOWNLOADS_DIR / f"{vid}.%(ext)s")
    is_yt = bool(YT_ID_RE.search(url or ""))
    fmt = (
        "18/22/best[ext=mp4][height<=480]/best[height<=360]/best"
        if is_yt
        else "best[ext=mp4]/best"
    )
    opts = _ydl_base(
        format=fmt,
        outtmpl=outtmpl,
        merge_output_format="mp4",
        ffmpeg_location=FFMPEG,
    )
    title = "Video"
    music_query = ""
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        duration = (info or {}).get("duration") or 0
        if duration and duration > max_seconds + 30:
            raise ValueError("too_long")
        title = ((info or {}).get("title") or title).strip()
        music_query = music_query_from_info(info)

    path = cached_file(vid, (".mp4", ".mkv", ".webm")) or _find_downloaded(vid)
    if not path:
        raise FileNotFoundError("video_not_found")
    if path.suffix.lower() != ".mp4":
        converted = DOWNLOADS_DIR / f"{vid}.mp4"
        _run_ffmpeg_sync(
            [
                "-y",
                "-i",
                str(path),
                "-t",
                str(max_seconds),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "32",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                str(converted),
            ]
        )
        path = converted
    if path.stat().st_size > TELEGRAM_MAX_FILE:
        raise ValueError("too_big")
    return path, title, music_query


def _extract_audio_sync(video_path: Path, cache_key: str) -> Path:
    cached = cached_file(cache_key, AUDIO_EXTS)
    if cached:
        return cached
    dest = DOWNLOADS_DIR / f"{cache_key}.m4a"
    _run_ffmpeg_sync(
        [
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            str(dest),
        ]
    )
    if not dest.exists() or dest.stat().st_size < 1000:
        raise FileNotFoundError("audio_not_found")
    return dest


def _run_ffmpeg_sync(args: list[str]) -> None:
    cmd = [FFMPEG, "-hide_banner", "-loglevel", FFMPEG_LOGLEVEL, "-threads", "0", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffmpeg failed")[-1500:]
        raise RuntimeError(err)


EFFECTS = {
    "8d": "apulsator=hz=0.12:amount=0.8",
    "echo": "aecho=0.8:0.88:60:0.4",
    "bass": "bass=g=10",
}


def _apply_effect_sync(src: Path, effect: str, cache_key: str | None = None) -> Path:
    af = EFFECTS.get(effect)
    if not af:
        raise ValueError("unknown_effect")
    if cache_key:
        cached = cached_file(f"{cache_key}_{effect}", (".m4a", ".mp3"))
        if cached:
            return cached
        dest = DOWNLOADS_DIR / f"{cache_key}_{effect}.m4a"
    else:
        dest = unique_path(".m4a")
    _run_ffmpeg_sync(
        [
            "-y",
            "-i",
            str(src),
            "-vn",
            "-af",
            af,
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-ac",
            "2",
            str(dest),
        ]
    )
    if dest.stat().st_size > TELEGRAM_MAX_FILE:
        raise ValueError("too_big")
    return dest


def _round_video_sync(src: Path) -> Path:
    dest = unique_path(".mp4")
    vf = "crop=min(iw\\,ih):min(iw\\,ih),scale=320:320,format=yuv420p"
    _run_ffmpeg_sync(
        [
            "-y",
            "-i",
            str(src),
            "-t",
            str(ROUND_SECONDS),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "32",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-ac",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    if dest.stat().st_size > TELEGRAM_MAX_FILE:
        raise ValueError("too_big")
    return dest


def _lock_for(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def search_music(query: str) -> list[dict]:
    key = " ".join((query or "").lower().split())
    hit = _search_cache.get(key)
    now = time.time()
    if hit and now - hit[0] < SEARCH_TTL:
        return hit[1]
    results = await asyncio.to_thread(_search_sync, query)
    if results:
        _search_cache[key] = (now, results)
        if len(_search_cache) > 200:
            oldest = min(_search_cache, key=lambda k: _search_cache[k][0])
            _search_cache.pop(oldest, None)
    return results


async def download_audio(url: str, video_id: str | None = None) -> Path:
    key = youtube_id(url, video_id)
    async with _lock_for(f"a:{key}"):
        return await asyncio.to_thread(_download_audio_sync, url, video_id)


async def download_video(url: str) -> tuple[Path, str, str]:
    key = youtube_id(url)
    async with _lock_for(f"v:{key}"):
        return await asyncio.to_thread(_download_video_sync, url)


async def extract_audio(video_path: Path, cache_key: str) -> Path:
    async with _lock_for(f"ea:{cache_key}"):
        return await asyncio.to_thread(_extract_audio_sync, video_path, cache_key)


async def apply_effect(src: Path, effect: str, cache_key: str | None = None) -> Path:
    return await asyncio.to_thread(_apply_effect_sync, src, effect, cache_key)


async def make_round_video(src: Path) -> Path:
    return await asyncio.to_thread(_round_video_sync, src)


def safe_filename(name: str, ext: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "file"
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{cleaned[:80]}{ext}"
