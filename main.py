from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import secrets
import string
import threading
from pathlib import Path
from typing import TypedDict, cast

import discord
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from waitress import serve

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.getenv("BOT_CONFIG_PATH", BASE_DIR / "bot_config.json"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
IS_RENDER = bool(os.getenv("RENDER"))
PORT = int(os.getenv("PORT", "10000"))


class MessageConfig(TypedDict):
    enabled: bool
    channel_id: str
    message: str


class ModerationConfig(TypedDict):
    enabled: bool
    blocked_words: list[str]
    warning: str


class AutoReplyConfig(TypedDict):
    trigger: str
    response: str
    match: str


class CommandConfig(TypedDict):
    name: str
    response: str


class BotConfig(TypedDict):
    bot_name: str
    prefix: str
    activity: str
    status: str
    welcome: MessageConfig
    goodbye: MessageConfig
    moderation: ModerationConfig
    auto_replies: list[AutoReplyConfig]
    custom_commands: list[CommandConfig]


DEFAULT_CONFIG: BotConfig = {
    "bot_name": "Community Bot",
    "prefix": "!",
    "activity": "コミュニティを見守っています",
    "status": "online",
    "welcome": {
        "enabled": True,
        "channel_id": "",
        "message": "{user} さん、**{server}** へようこそ！",
    },
    "goodbye": {
        "enabled": False,
        "channel_id": "",
        "message": "**{username}** さんがサーバーを退出しました。",
    },
    "moderation": {
        "enabled": False,
        "blocked_words": [],
        "warning": "{user} この言葉は使用できません。",
    },
    "auto_replies": [
        {
            "trigger": "おはよう",
            "response": "おはようございます！今日もよい一日を。",
            "match": "contains",
        }
    ],
    "custom_commands": [
        {"name": "rules", "response": "サーバールールを確認してください。"},
        {"name": "support", "response": "困ったときは管理者へお問い合わせください。"},
    ],
}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord-bot-builder")


class ConfigError(ValueError):
    pass


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self._config = self._load()

    def _load(self) -> BotConfig:
        if not self.path.exists():
            self._write(DEFAULT_CONFIG)
            return copy.deepcopy(DEFAULT_CONFIG)

        try:
            stored = cast(object, json.loads(self.path.read_text(encoding="utf-8")))
            return validate_config(stored)
        except (OSError, json.JSONDecodeError, ConfigError) as error:
            logger.error("設定ファイルを読み込めません: %s", error)
            return copy.deepcopy(DEFAULT_CONFIG)

    def _write(self, config: BotConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def get(self) -> BotConfig:
        with self.lock:
            return copy.deepcopy(self._config)

    def save(self, config: object) -> BotConfig:
        validated = validate_config(config)
        with self.lock:
            self._write(validated)
            self._config = validated
            return copy.deepcopy(validated)


def require_text(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 2000,
) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{field} は文字列で入力してください。")
    normalized = value.strip()
    if len(normalized) < minimum:
        raise ConfigError(f"{field} は{minimum}文字以上で入力してください。")
    if len(normalized) > maximum:
        raise ConfigError(f"{field} は{maximum}文字以内で入力してください。")
    return normalized


def require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{field} の値が正しくありません。")
    return value


def require_template(value: object, field: str, *, maximum: int) -> str:
    template = require_text(value, field, minimum=1, maximum=maximum)
    allowed_fields = {"user", "username", "server", "member_count"}
    try:
        for _, field_name, format_spec, conversion in string.Formatter().parse(template):
            if field_name and field_name not in allowed_fields:
                raise ConfigError(f"{field}で使用できない変数「{field_name}」があります。")
            if format_spec or conversion:
                raise ConfigError(f"{field}では書式指定を使用できません。")
    except ValueError as error:
        raise ConfigError(f"{field}の波括弧が正しくありません。") from error
    return template


def validate_config(raw: object) -> BotConfig:
    if not isinstance(raw, dict):
        raise ConfigError("設定データの形式が正しくありません。")
    raw_config = cast(dict[str, object], raw)

    prefix = require_text(
        raw_config.get("prefix"),
        "コマンド接頭辞",
        minimum=1,
        maximum=5,
    )
    if any(character.isspace() for character in prefix):
        raise ConfigError("コマンド接頭辞に空白は使用できません。")

    status = require_text(raw_config.get("status"), "ステータス")
    if status not in {"online", "idle", "dnd", "invisible"}:
        raise ConfigError("ステータスの値が正しくありません。")

    message_sections: dict[str, MessageConfig] = {}
    for section_name, label in (("welcome", "参加メッセージ"), ("goodbye", "退出メッセージ")):
        section = raw_config.get(section_name)
        if not isinstance(section, dict):
            raise ConfigError(f"{label}の設定が正しくありません。")
        section_config = cast(dict[str, object], section)
        channel_id = require_text(
            section_config.get("channel_id", ""),
            f"{label}のチャンネルID",
        )
        if channel_id and not channel_id.isdigit():
            raise ConfigError(f"{label}のチャンネルIDは数字で入力してください。")
        message_sections[section_name] = {
            "enabled": require_bool(
                section_config.get("enabled"),
                f"{label}の有効状態",
            ),
            "channel_id": channel_id,
            "message": require_template(
                section_config.get("message"),
                f"{label}の本文",
                maximum=1000,
            ),
        }

    moderation = raw_config.get("moderation")
    if not isinstance(moderation, dict):
        raise ConfigError("モデレーション設定が正しくありません。")
    moderation_config = cast(dict[str, object], moderation)
    blocked_words = moderation_config.get("blocked_words")
    if not isinstance(blocked_words, list) or len(blocked_words) > 100:
        raise ConfigError("禁止ワードは100件以内で設定してください。")
    validated_moderation: ModerationConfig = {
        "enabled": require_bool(
            moderation_config.get("enabled"),
            "モデレーションの有効状態",
        ),
        "blocked_words": [
            require_text(word, "禁止ワード", minimum=1, maximum=100)
            for word in blocked_words
        ],
        "warning": require_template(
            moderation_config.get("warning"),
            "警告メッセージ",
            maximum=500,
        ),
    }

    auto_replies = raw_config.get("auto_replies")
    if not isinstance(auto_replies, list) or len(auto_replies) > 50:
        raise ConfigError("自動返信は50件以内で設定してください。")
    validated_replies: list[AutoReplyConfig] = []
    for index, reply in enumerate(auto_replies, start=1):
        if not isinstance(reply, dict):
            raise ConfigError(f"自動返信 {index} の形式が正しくありません。")
        reply_config = cast(dict[str, object], reply)
        match = require_text(
            reply_config.get("match"),
            f"自動返信 {index} の判定方法",
        )
        if match not in {"contains", "exact"}:
            raise ConfigError(f"自動返信 {index} の判定方法が正しくありません。")
        validated_replies.append(
            {
                "trigger": require_text(
                    reply_config.get("trigger"),
                    f"自動返信 {index} のキーワード",
                    minimum=1,
                    maximum=100,
                ),
                "response": require_text(
                    reply_config.get("response"),
                    f"自動返信 {index} の本文",
                    minimum=1,
                ),
                "match": match,
            }
        )
    custom_commands = raw_config.get("custom_commands")
    if not isinstance(custom_commands, list) or len(custom_commands) > 50:
        raise ConfigError("カスタムコマンドは50件以内で設定してください。")
    validated_commands: list[CommandConfig] = []
    command_names: set[str] = set()
    reserved_names = {"help", "ping", "server", "avatar"}
    for index, command in enumerate(custom_commands, start=1):
        if not isinstance(command, dict):
            raise ConfigError(f"コマンド {index} の形式が正しくありません。")
        command_config = cast(dict[str, object], command)
        name = require_text(
            command_config.get("name"),
            f"コマンド {index} の名前",
            minimum=1,
            maximum=32,
        ).lower()
        if not re.fullmatch(r"[a-z0-9_-]+", name):
            raise ConfigError("コマンド名には半角英数字・_・-のみ使用できます。")
        if name in command_names or name in reserved_names:
            raise ConfigError(f"コマンド名「{name}」は重複または予約されています。")
        command_names.add(name)
        validated_commands.append(
            {
                "name": name,
                "response": require_text(
                    command_config.get("response"),
                    f"コマンド {name} の返信",
                    minimum=1,
                ),
            }
        )
    return {
        "bot_name": require_text(
            raw_config.get("bot_name"),
            "Bot名",
            minimum=1,
            maximum=80,
        ),
        "prefix": prefix,
        "activity": require_text(
            raw_config.get("activity"),
            "アクティビティ",
            maximum=128,
        ),
        "status": status,
        "welcome": message_sections["welcome"],
        "goodbye": message_sections["goodbye"],
        "moderation": validated_moderation,
        "auto_replies": validated_replies,
        "custom_commands": validated_commands,
    }


class SafeFormatValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def format_message(template: str, member: discord.Member) -> str:
    return template.format_map(
        SafeFormatValues(
            user=member.mention,
            username=member.display_name,
            server=member.guild.name,
            member_count=str(member.guild.member_count),
        )
    )


def configured_channel(
    guild: discord.Guild,
    channel_id: str,
) -> discord.TextChannel | None:
    if channel_id:
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            return channel
    return guild.system_channel


config_store = ConfigStore(CONFIG_PATH)


class CustomDiscordBot(discord.Client):
    event_loop: asyncio.AbstractEventLoop | None = None

    async def setup_hook(self) -> None:
        self.event_loop = asyncio.get_running_loop()

    async def on_ready(self) -> None:
        await self.apply_presence()
        logger.info("%s としてDiscordへ接続しました。", self.user)

    async def apply_presence(self) -> None:
        config = config_store.get()
        statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        activity = (
            discord.Game(name=config["activity"]) if config["activity"] else None
        )
        await self.change_presence(
            status=statuses[config["status"]],
            activity=activity,
        )

    async def on_member_join(self, member: discord.Member) -> None:
        welcome = config_store.get()["welcome"]
        if not welcome["enabled"]:
            return
        channel = configured_channel(member.guild, welcome["channel_id"])
        if channel:
            await channel.send(
                format_message(welcome["message"], member),
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False,
                ),
            )

    async def on_member_remove(self, member: discord.Member) -> None:
        goodbye = config_store.get()["goodbye"]
        if not goodbye["enabled"]:
            return
        channel = configured_channel(member.guild, goodbye["channel_id"])
        if channel:
            await channel.send(
                format_message(goodbye["message"], member),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content:
            return

        config = config_store.get()
        content = message.content.strip()
        normalized_content = content.casefold()

        moderation = config["moderation"]
        if moderation["enabled"] and message.guild:
            blocked_word = next(
                (
                    word
                    for word in moderation["blocked_words"]
                    if word.casefold() in normalized_content
                ),
                None,
            )
            if blocked_word:
                try:
                    await message.delete()
                    if not isinstance(message.author, discord.Member):
                        return
                    warning = format_message(
                        moderation["warning"],
                        message.author,
                    )
                    await message.channel.send(
                        warning,
                        delete_after=8,
                        allowed_mentions=discord.AllowedMentions(
                            users=True,
                            roles=False,
                            everyone=False,
                        ),
                    )
                except discord.Forbidden:
                    logger.warning("メッセージ削除権限がありません: guild=%s", message.guild.id)
                return

        if content.startswith(config["prefix"]):
            await self.handle_command(message, config)
            return

        for reply in config["auto_replies"]:
            trigger = reply["trigger"].casefold()
            matches = (
                normalized_content == trigger
                if reply["match"] == "exact"
                else trigger in normalized_content
            )
            if matches:
                await message.channel.send(
                    reply["response"],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

    async def handle_command(
        self,
        message: discord.Message,
        config: BotConfig,
    ) -> None:
        command_name = (
            message.content[len(config["prefix"]) :].strip().split(maxsplit=1)[0].lower()
            if message.content[len(config["prefix"]) :].strip()
            else ""
        )
        if not command_name:
            return

        custom_commands = {
            command["name"]: command["response"]
            for command in config["custom_commands"]
        }
        response: str | None = None

        if command_name == "help":
            custom_names = ", ".join(
                f"`{config['prefix']}{name}`" for name in custom_commands
            )
            response = (
                f"**{config['bot_name']} コマンド**\n"
                f"`{config['prefix']}help` `ping` `server` `avatar`"
            )
            if custom_names:
                response += f"\nカスタム: {custom_names}"
        elif command_name == "ping":
            response = f"Pong! `{round(self.latency * 1000)}ms`"
        elif command_name == "server" and message.guild:
            response = (
                f"**{message.guild.name}**\n"
                f"メンバー: {message.guild.member_count}人\n"
                f"作成日: {discord.utils.format_dt(message.guild.created_at, style='D')}"
            )
        elif command_name == "avatar":
            response = message.author.display_avatar.url
        elif command_name in custom_commands:
            response = custom_commands[command_name]

        if response:
            await message.channel.send(
                response,
                allowed_mentions=discord.AllowedMentions.none(),
            )


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
discord_bot = CustomDiscordBot(intents=intents)

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_RENDER,
)


def authentication_state() -> tuple[bool, bool]:
    setup_required = IS_RENDER and not ADMIN_PASSWORD
    logged_in = not ADMIN_PASSWORD or bool(session.get("authenticated"))
    return logged_in, setup_required


def api_auth_error() -> tuple[Response, int] | None:
    logged_in, setup_required = authentication_state()
    if setup_required:
        return jsonify({"error": "RenderでADMIN_PASSWORDを設定してください。"}), 503
    if not logged_in:
        return jsonify({"error": "ログインが必要です。"}), 401
    return None


@app.get("/")
def index() -> str:
    logged_in, setup_required = authentication_state()
    return render_template(
        "index.html",
        logged_in=logged_in,
        setup_required=setup_required,
        password_enabled=bool(ADMIN_PASSWORD),
    )


@app.post("/login")
def login() -> ResponseReturnValue:
    if ADMIN_PASSWORD and secrets.compare_digest(
        request.form.get("password", ""),
        ADMIN_PASSWORD,
    ):
        session["authenticated"] = True
        return redirect(url_for("index"))
    return redirect(url_for("index", login_error="1"))


@app.post("/logout")
def logout() -> ResponseReturnValue:
    session.clear()
    return redirect(url_for("index"))


@app.get("/api/config")
def get_config() -> Response | tuple[Response, int]:
    auth_error = api_auth_error()
    if auth_error:
        return auth_error
    return jsonify(config_store.get())


@app.put("/api/config")
def update_config() -> Response | tuple[Response, int]:
    auth_error = api_auth_error()
    if auth_error:
        return auth_error
    try:
        updated = config_store.save(request.get_json(silent=True))
    except ConfigError as error:
        return jsonify({"error": str(error)}), 400
    except OSError:
        logger.exception("設定ファイルを保存できません。")
        return jsonify({"error": "設定ファイルを保存できませんでした。"}), 500

    if discord_bot.is_ready() and discord_bot.event_loop:
        asyncio.run_coroutine_threadsafe(
            discord_bot.apply_presence(),
            discord_bot.event_loop,
        )
    return jsonify(updated)


@app.get("/api/status")
def status() -> Response:
    return jsonify(
        {
            "bot_connected": discord_bot.is_ready(),
            "guild_count": len(discord_bot.guilds) if discord_bot.is_ready() else 0,
            "configuration_locked": IS_RENDER and not ADMIN_PASSWORD,
        }
    )


@app.get("/health")
def health() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200


def run_discord_bot() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        logger.warning("DISCORD_TOKENが未設定のため、ダッシュボードのみ起動します。")
        return
    try:
        discord_bot.run(token, log_handler=None)
    except discord.LoginFailure:
        logger.error("DISCORD_TOKENが無効です。")
    except Exception:
        logger.exception("Discord Botの起動中にエラーが発生しました。")


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
    bot_thread.start()
    serve(app, host="0.0.0.0", port=PORT)
