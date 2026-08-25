from __future__ import annotations

import asyncio
import contextlib
import html
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import BOT_TOKEN, DOWNLOADS_DIR
from i18n import t
from media import (
    apply_effect,
    download_audio,
    download_video,
    extract_audio,
    extract_url,
    format_duration,
    make_round_video,
    safe_filename,
    search_music,
    youtube_id,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("muzika")

router = Router()


class Form(StatesGroup):
    waiting_round = State()


@dataclass
class UserData:
    lang: str = "ru"
    results: list[dict] = field(default_factory=list)
    audio_path: Path | None = None
    video_path: Path | None = None
    track_url: str | None = None
    title: str = ""
    performer: str = ""
    duration: int | None = None
    last_query: str = ""
    want_video: bool = False
    track_id: str | None = None
    is_clip: bool = False
    clip_query: str = ""


USERS: dict[int, UserData] = {}
FILE_IDS: dict[str, str] = {}
FILE_ID_STORE = DOWNLOADS_DIR / "file_ids.json"
PREFETCH_COUNT = 3
_prefetching: set[str] = set()


def load_file_ids() -> None:
    try:
        FILE_IDS.update(json.loads(FILE_ID_STORE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


def save_file_ids() -> None:
    try:
        FILE_ID_STORE.write_text(
            json.dumps(FILE_IDS, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def user(uid: int) -> UserData:
    if uid not in USERS:
        USERS[uid] = UserData()
    return USERS[uid]


def cache_file_id(key: str | None, message: Message | None) -> None:
    if not key or not message:
        return
    media = message.audio or message.video or message.document
    if media:
        FILE_IDS[key] = media.file_id
        save_file_ids()


async def prefetch_audio(results: list[dict]) -> None:
    """Warm the cache for the first few results so taps feel instant."""
    for track in results[:PREFETCH_COUNT]:
        tid = track.get("id")
        if not tid or f"a:{tid}" in FILE_IDS or tid in _prefetching:
            continue
        _prefetching.add(tid)
        try:
            await download_audio(track["url"], tid)
        except Exception:
            log.debug("prefetch failed for %s", tid)
        finally:
            _prefetching.discard(tid)


def lang_from_tg(from_user) -> str:
    code = (getattr(from_user, "language_code", None) or "").lower()
    if code.startswith(("tg", "tj")):
        return "tg"
    if code.startswith("en"):
        return "en"
    return "ru"


def format_results_text(query: str, results: list[dict]) -> str:
    q = html.escape((query or "").strip()[:80])
    lines = [f"🎵 <b>{q}</b>", ""]
    for i, item in enumerate(results, 1):
        title = html.escape((item.get("title") or "Unknown")[:90])
        dur = format_duration(item.get("duration"))
        lines.append(f"{i}. {title}  {dur}".rstrip())
    return "\n".join(lines)


def tracks_keyboard(results: list[dict], lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t(lang, "btn_video"), callback_data="wantvid")]
    ]
    nums: list[InlineKeyboardButton] = []
    for i in range(len(results)):
        nums.append(InlineKeyboardButton(text=str(i + 1), callback_data=f"pick:{i}"))
        if len(nums) == 5:
            rows.append(nums)
            nums = []
    if nums:
        rows.append(nums)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def actions_keyboard(lang: str, full_song: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, "btn_effects"), callback_data="fxmenu")],
        [
            InlineKeyboardButton(text=f"⬇️ {t(lang, 'dl_audio')}", callback_data="dl:audio"),
            InlineKeyboardButton(text=f"🎬 {t(lang, 'dl_video')}", callback_data="dl:video"),
        ],
    ]
    if full_song:
        rows.insert(
            0, [InlineKeyboardButton(text=t(lang, "btn_full_song"), callback_data="fullsong")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def effects_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🎧 {t(lang, 'fx_8d')}", callback_data="fx:8d"),
                InlineKeyboardButton(text=f"🔊 {t(lang, 'fx_echo')}", callback_data="fx:echo"),
                InlineKeyboardButton(text=f"🎸 {t(lang, 'fx_bass')}", callback_data="fx:bass"),
            ],
            [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="fxback")],
        ]
    )


def fx_label(lang: str, code: str) -> str:
    return {"8d": t(lang, "fx_8d"), "echo": t(lang, "fx_echo"), "bass": t(lang, "fx_bass")}.get(
        code, code
    )


async def keep_chat_action(bot: Bot, chat_id: int, action: ChatAction) -> None:
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        return
    except Exception:
        return


async def with_chat_action(bot: Bot, chat_id: int, action: ChatAction, coro):
    task = asyncio.create_task(keep_chat_action(bot, chat_id, action))
    try:
        return await coro
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def ensure_audio(u: UserData) -> Path | None:
    if u.audio_path and u.audio_path.exists():
        return u.audio_path
    if u.video_path and u.video_path.exists():
        key = u.track_id or youtube_id(u.track_url or "clip")
        u.audio_path = await extract_audio(u.video_path, key)
        return u.audio_path
    return None


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    u = user(message.from_user.id)
    u.lang = lang_from_tg(message.from_user)
    await message.answer(t(u.lang, "welcome"))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    u = user(message.from_user.id)
    await message.answer(t(u.lang, "help"))


@router.message(Command("round", "raund"))
async def cmd_round(message: Message, state: FSMContext) -> None:
    u = user(message.from_user.id)
    if message.video or message.video_note or (
        message.document and (message.document.mime_type or "").startswith("video/")
    ):
        await process_round(message, u)
        return
    await state.set_state(Form.waiting_round)
    await message.answer(t(u.lang, "round_ask"))


@router.callback_query(F.data == "fxmenu")
async def on_fx_menu(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    await callback.answer()
    with contextlib.suppress(Exception):
        await callback.message.edit_reply_markup(reply_markup=effects_keyboard(u.lang))


@router.callback_query(F.data == "fxback")
async def on_fx_back(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    await callback.answer()
    with contextlib.suppress(Exception):
        await callback.message.edit_reply_markup(
            reply_markup=actions_keyboard(u.lang, full_song=u.is_clip)
        )


@router.callback_query(F.data == "fullsong")
async def on_full_song(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    query = (u.clip_query or u.title or "").strip()
    if not query:
        await callback.answer(t(u.lang, "need_track"), show_alert=True)
        return
    await callback.answer()
    status = await callback.message.answer(t(u.lang, "searching_full"))
    try:
        results = await search_music(query)
    except Exception:
        log.exception("full song search failed")
        await status.edit_text(t(u.lang, "error"))
        return
    if not results:
        await status.edit_text(t(u.lang, "not_found"))
        return
    u.results = results
    u.last_query = query
    u.want_video = False
    await status.edit_text(
        format_results_text(query, results),
        reply_markup=tracks_keyboard(results, u.lang),
    )
    asyncio.create_task(prefetch_audio(results))


@router.callback_query(F.data == "wantvid")
async def on_want_video(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    if not u.results:
        await callback.answer(t(u.lang, "need_track"), show_alert=True)
        return
    u.want_video = True
    await callback.answer(t(u.lang, "pick_for_video"))


@router.callback_query(F.data.startswith("pick:"))
async def on_pick(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    try:
        idx = int(callback.data.split(":", 1)[1])
        track = u.results[idx]
    except (ValueError, IndexError):
        await callback.answer(t(u.lang, "need_track"), show_alert=True)
        return
    send_video = u.want_video
    u.want_video = False
    await callback.answer()
    u.track_url = track["url"]
    u.track_id = track.get("id")
    u.title = track["title"]
    u.performer = track.get("uploader") or "YouTube"
    u.duration = track.get("duration")
    u.is_clip = False
    u.audio_path = None
    u.video_path = None
    chat_id = callback.message.chat.id
    bot = callback.bot
    if send_video:
        cache_key = f"v:{u.track_id}"
        cached_id = FILE_IDS.get(cache_key)
        if cached_id:
            await callback.message.answer_video(
                cached_id,
                caption=u.title[:1024],
                supports_streaming=True,
                reply_markup=actions_keyboard(u.lang),
            )
            return
        try:
            path, title, _q = await with_chat_action(
                bot, chat_id, ChatAction.UPLOAD_VIDEO, download_video(track["url"])
            )
            u.video_path = path
            if title:
                u.title = title
            sent = await callback.message.answer_video(
                FSInputFile(path, filename=safe_filename(u.title, path.suffix)),
                caption=u.title[:1024],
                supports_streaming=True,
                reply_markup=actions_keyboard(u.lang),
            )
            cache_file_id(cache_key, sent)
        except ValueError as exc:
            key = str(exc) if str(exc) in ("too_big", "too_long") else "error"
            await callback.message.answer(t(u.lang, key))
        except Exception:
            log.exception("pick video failed")
            await callback.message.answer(t(u.lang, "bad_link"))
        return
    audio_key = f"a:{u.track_id}"
    cached_id = FILE_IDS.get(audio_key)
    if cached_id:
        await callback.message.answer_audio(
            cached_id,
            caption=t(u.lang, "audio_ready"),
            reply_markup=actions_keyboard(u.lang),
        )
        return
    try:
        path = await with_chat_action(
            bot,
            chat_id,
            ChatAction.UPLOAD_VOICE,
            download_audio(track["url"], track.get("id")),
        )
    except ValueError as exc:
        key = str(exc) if str(exc) in ("too_big", "too_long") else "error"
        await callback.message.answer(t(u.lang, key))
        return
    except Exception:
        log.exception("audio download failed")
        await callback.message.answer(t(u.lang, "error"))
        return
    u.audio_path = path
    try:
        sent = await callback.message.answer_audio(
            FSInputFile(path, filename=safe_filename(u.title, path.suffix)),
            title=u.title[:64],
            performer=u.performer[:64],
            duration=u.duration,
            caption=t(u.lang, "audio_ready"),
            reply_markup=actions_keyboard(u.lang),
        )
        cache_file_id(audio_key, sent)
    except Exception:
        log.exception("send audio failed")
        await callback.message.answer(t(u.lang, "error"))


@router.callback_query(F.data.startswith("fx:"))
async def on_fx(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    effect = callback.data.split(":", 1)[1]
    if not await ensure_audio(u):
        await callback.answer(t(u.lang, "need_track"), show_alert=True)
        return
    await callback.answer()
    name = fx_label(u.lang, effect)
    fx_key = f"fx:{u.track_id}:{effect}"
    cached_id = FILE_IDS.get(fx_key)
    if cached_id:
        await callback.message.answer_audio(
            cached_id, caption=t(u.lang, "fx_done", fx=name)
        )
        return
    try:
        out = await with_chat_action(
            callback.bot,
            callback.message.chat.id,
            ChatAction.RECORD_VOICE,
            apply_effect(u.audio_path, effect, u.track_id),
        )
        sent = await callback.message.answer_audio(
            FSInputFile(out, filename=safe_filename(f"{u.title} {name}", out.suffix)),
            title=f"{u.title[:50]} [{name}]"[:64],
            performer=u.performer[:64],
            caption=t(u.lang, "fx_done", fx=name),
        )
        cache_file_id(fx_key, sent)
    except Exception:
        log.exception("effect failed")
        await callback.message.answer(t(u.lang, "error"))


@router.callback_query(F.data == "dl:audio")
async def on_dl_audio(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    if not await ensure_audio(u):
        await callback.answer(t(u.lang, "need_track"), show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.answer_document(
            FSInputFile(u.audio_path, filename=safe_filename(u.title, u.audio_path.suffix)),
            caption=t(u.lang, "file_song"),
        )
    except Exception:
        log.exception("send document failed")
        await callback.message.answer(t(u.lang, "error"))


@router.callback_query(F.data == "dl:video")
async def on_dl_video(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    if u.video_path and u.video_path.exists():
        await callback.answer()
        try:
            await callback.message.answer_document(
                FSInputFile(
                    u.video_path,
                    filename=safe_filename(u.title or "video", u.video_path.suffix),
                )
            )
        except Exception:
            log.exception("send saved video failed")
            await callback.message.answer(t(u.lang, "error"))
        return
    if not u.track_url:
        await callback.answer(t(u.lang, "need_track"), show_alert=True)
        return
    await callback.answer()
    try:
        path, _title, _q = await with_chat_action(
            callback.bot,
            callback.message.chat.id,
            ChatAction.UPLOAD_VIDEO,
            download_video(u.track_url),
        )
        u.video_path = path
        await callback.message.answer_document(
            FSInputFile(path, filename=safe_filename(u.title, path.suffix))
        )
    except ValueError as exc:
        key = str(exc) if str(exc) in ("too_big", "too_long") else "error"
        await callback.message.answer(t(u.lang, key))
    except Exception:
        log.exception("video download failed")
        await callback.message.answer(t(u.lang, "bad_link"))


@router.message(Form.waiting_round, F.video | F.video_note | F.document)
async def on_round_video(message: Message, state: FSMContext) -> None:
    u = user(message.from_user.id)
    await state.clear()
    await process_round(message, u)


@router.message(Form.waiting_round)
async def on_round_not_video(message: Message) -> None:
    u = user(message.from_user.id)
    await message.answer(t(u.lang, "need_video"))


async def process_round(message: Message, u: UserData) -> None:
    file = message.video or message.video_note or message.document
    if not file:
        await message.answer(t(u.lang, "need_video"))
        return
    status = await message.answer(t(u.lang, "round_wait"))
    src = DOWNLOADS_DIR / f"in_{message.from_user.id}_{file.file_unique_id}.mp4"
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    try:
        await message.bot.download(file, destination=src)
        out = await make_round_video(src)
        await message.answer_video_note(FSInputFile(out))
        await message.answer(t(u.lang, "round_done"))
        await status.delete()
    except Exception:
        log.exception("round video failed")
        await status.edit_text(t(u.lang, "error"))
    finally:
        try:
            src.unlink(missing_ok=True)
        except OSError:
            pass


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(message: Message, state: FSMContext) -> None:
    u = user(message.from_user.id)
    text = (message.text or "").strip()
    if not text:
        return
    url = extract_url(text)
    if url:
        await state.clear()
        try:
            path, title, music_query = await with_chat_action(
                message.bot, message.chat.id, ChatAction.UPLOAD_VIDEO, download_video(url)
            )
            u.video_path = path
            u.track_url = url
            u.track_id = youtube_id(url)
            u.title = title or "Video"
            u.is_clip = True
            u.clip_query = music_query or u.title
            u.performer = ""
            u.duration = None
            try:
                u.audio_path = await extract_audio(path, u.track_id)
            except Exception:
                log.exception("extract audio from link failed")
                u.audio_path = None
            await message.answer_video(
                FSInputFile(path, filename=safe_filename(u.title, path.suffix)),
                caption=u.title[:1024],
                supports_streaming=True,
                reply_markup=actions_keyboard(u.lang, full_song=True),
            )
        except ValueError as exc:
            key = str(exc) if str(exc) in ("too_big", "too_long") else "bad_link"
            await message.answer(t(u.lang, key))
        except Exception:
            log.exception("link download failed")
            await message.answer(t(u.lang, "bad_link"))
        return

    if len(text) < 2:
        await message.answer(t(u.lang, "query_short"))
        return

    await state.clear()
    status = await message.answer(t(u.lang, "searching"))
    try:
        results = await search_music(text)
    except Exception:
        log.exception("search failed")
        await status.edit_text(t(u.lang, "error"))
        return
    if not results:
        await status.edit_text(t(u.lang, "not_found"))
        return
    u.results = results
    u.last_query = text
    u.want_video = False
    await status.edit_text(
        format_results_text(text, results),
        reply_markup=tracks_keyboard(results, u.lang),
    )
    asyncio.create_task(prefetch_audio(results))


@router.callback_query(F.data == "savedvid")
async def on_savedvid(callback: CallbackQuery) -> None:
    u = user(callback.from_user.id)
    path = u.video_path
    if path and path.exists():
        await callback.answer()
        try:
            await callback.message.answer_document(
                FSInputFile(path, filename=safe_filename(u.title or "video", ".mp4"))
            )
        except Exception:
            log.exception("saved video send failed")
            await callback.message.answer(t(u.lang, "error"))
        return
    if not u.track_url:
        await callback.answer(t(u.lang, "need_track"), show_alert=True)
        return
    await callback.answer()
    status = await callback.message.answer(t(u.lang, "downloading_video"))
    try:
        path, _title, _q = await download_video(u.track_url)
        u.video_path = path
        await callback.message.answer_document(
            FSInputFile(path, filename=safe_filename(u.title or "video", ".mp4"))
        )
        await status.delete()
    except Exception:
        log.exception("saved video send failed")
        await status.edit_text(t(u.lang, "error"))


async def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN.startswith("1234567890"):
        print(
            "Put your Telegram bot token in .env\n"
            "1) Open Telegram, find @BotFather\n"
            "2) /newbot — create a bot\n"
            "3) Copy the token\n"
            "4) Create .env file: BOT_TOKEN=your_token"
        )
        sys.exit(1)
    load_file_ids()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    log.info("Bot starting")
    while True:
        try:
            await dp.start_polling(bot, handle_signals=False)
            return
        except (KeyboardInterrupt, SystemExit):
            return
        except Exception:
            log.exception("polling crashed, reconnecting in 5s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
