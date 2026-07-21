from __future__ import annotations

import random
import re
import asyncio
from contextlib import asynccontextmanager
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/birthdays.db"))
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Almaty")
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("birthday-bot")


def validate_date(day: int, month: int, year: Optional[int] = None) -> bool:
    """Validate a birthday. Leap-day birthdays are allowed."""
    validation_year = year if year is not None else 2000
    try:
        date(validation_year, month, day)
        return True
    except ValueError:
        return False


def format_birthday(day: int, month: int, year: Optional[int]) -> str:
    months = (
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    result = f"{day} {months[month]}"
    if year:
        result += f" {year} года"
    return result


def next_birthday(day: int, month: int, today: date) -> date:
    """Return the next occurrence. Feb 29 is treated as Feb 28 in non-leap years."""
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            candidate = date(year, 2, 28)
        if candidate >= today:
            return candidate
    raise RuntimeError("Could not calculate the next birthday")


class Database:
    def __init__(self, path: Path):
        self.path = path

    @asynccontextmanager
    async def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path)
        try:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
            yield db
        finally:
            await db.close()

    async def initialize(self) -> None:
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS birthdays (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    birth_day INTEGER NOT NULL CHECK (birth_day BETWEEN 1 AND 31),
                    birth_month INTEGER NOT NULL CHECK (birth_month BETWEEN 1 AND 12),
                    birth_year INTEGER,
                    created_by INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    announcement_channel_id INTEGER,
                    timezone TEXT NOT NULL DEFAULT 'Asia/Almaty',
                    announcement_hour INTEGER NOT NULL DEFAULT 9
                        CHECK (announcement_hour BETWEEN 0 AND 23),
                    announcement_message TEXT NOT NULL DEFAULT
                        '🎂 Сегодня день рождения у {mention}! Поздравляем! 🎉'
                );

                CREATE TABLE IF NOT EXISTS sent_announcements (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    birthday_date TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id, birthday_date)
                );

                CREATE INDEX IF NOT EXISTS idx_birthdays_date
                ON birthdays(guild_id, birth_month, birth_day);
                """
            )
            await db.commit()

    async def ensure_guild(self, guild_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO guild_settings
                    (guild_id, timezone, announcement_hour, announcement_message)
                VALUES (?, ?, 9, '🎂 Сегодня день рождения у {mention}! Поздравляем! 🎉')
                """,
                (guild_id, DEFAULT_TIMEZONE),
            )
            await db.commit()

    async def set_birthday(
        self,
        guild_id: int,
        user_id: int,
        day: int,
        month: int,
        year: Optional[int],
        created_by: int,
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO birthdays (
                    guild_id, user_id, birth_day, birth_month,
                    birth_year, created_by, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    birth_day = excluded.birth_day,
                    birth_month = excluded.birth_month,
                    birth_year = excluded.birth_year,
                    created_by = excluded.created_by,
                    updated_at = excluded.updated_at
                """,
                (
                    guild_id, user_id, day, month, year, created_by,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            await db.commit()

    async def remove_birthday(self, guild_id: int, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_birthday(self, guild_id: int, user_id: int):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT birth_day, birth_month, birth_year
                FROM birthdays
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            return await cursor.fetchone()

    async def get_birthdays(self, guild_id: int):
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT user_id, birth_day, birth_month, birth_year
                FROM birthdays
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            return await cursor.fetchall()

    async def get_settings(self, guild_id: int):
        await self.ensure_guild(guild_id)
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            return await cursor.fetchone()

    async def set_channel(self, guild_id: int, channel_id: int) -> None:
        await self.ensure_guild(guild_id)
        async with self.connect() as db:
            await db.execute(
                """
                UPDATE guild_settings
                SET announcement_channel_id = ?
                WHERE guild_id = ?
                """,
                (channel_id, guild_id),
            )
            await db.commit()

    async def set_timezone(self, guild_id: int, timezone_name: str) -> None:
        await self.ensure_guild(guild_id)
        async with self.connect() as db:
            await db.execute(
                "UPDATE guild_settings SET timezone = ? WHERE guild_id = ?",
                (timezone_name, guild_id),
            )
            await db.commit()

    async def set_hour(self, guild_id: int, hour: int) -> None:
        await self.ensure_guild(guild_id)
        async with self.connect() as db:
            await db.execute(
                "UPDATE guild_settings SET announcement_hour = ? WHERE guild_id = ?",
                (hour, guild_id),
            )
            await db.commit()

    async def set_message(self, guild_id: int, message: str) -> None:
        await self.ensure_guild(guild_id)
        async with self.connect() as db:
            await db.execute(
                "UPDATE guild_settings SET announcement_message = ? WHERE guild_id = ?",
                (message, guild_id),
            )
            await db.commit()

    async def was_sent(
        self, guild_id: int, user_id: int, birthday_date: str
    ) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM sent_announcements
                WHERE guild_id = ? AND user_id = ? AND birthday_date = ?
                """,
                (guild_id, user_id, birthday_date),
            )
            return await cursor.fetchone() is not None

    async def mark_sent(
        self, guild_id: int, user_id: int, birthday_date: str
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO sent_announcements
                    (guild_id, user_id, birthday_date, sent_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    guild_id, user_id, birthday_date,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            await db.commit()


class BirthdayBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.db = Database(DATABASE_PATH)

    async def setup_hook(self) -> None:
        await self.db.initialize()
        self.tree.add_command(BirthdayCommands(self))
        self.tree.add_command(BirthdayAdminCommands(self))

        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s commands to development guild %s", len(synced), DEV_GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

        self.birthday_check.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")

    async def close(self) -> None:
        self.birthday_check.cancel()
        await super().close()

    @tasks.loop(minutes=1)
    async def birthday_check(self) -> None:
        for guild in self.guilds:
            try:
                await self.process_guild_birthdays(guild)
            except Exception:
                log.exception("Birthday check failed for guild %s", guild.id)

    @birthday_check.before_loop
    async def before_birthday_check(self) -> None:
        await self.wait_until_ready()

    async def process_guild_birthdays(
        self, guild: discord.Guild, force: bool = False
    ) -> int:
        settings = await self.db.get_settings(guild.id)
        channel_id = settings["announcement_channel_id"]
        if not channel_id:
            return 0

        try:
            tz = ZoneInfo(settings["timezone"])
        except ZoneInfoNotFoundError:
            log.error("Invalid timezone configured for guild %s", guild.id)
            return 0

        now = datetime.now(tz)
        if not force and now.hour < settings["announcement_hour"]:
            return 0

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.warning("Announcement channel is unavailable in guild %s", guild.id)
            return 0

        rows = await self.db.get_birthdays(guild.id)
        sent_count = 0
        birthday_key = now.date().isoformat()

        for row in rows:
            is_today = row["birth_day"] == now.day and row["birth_month"] == now.month

            # Celebrate Feb 29 birthdays on Feb 28 in non-leap years.
            if (
                row["birth_day"] == 29
                and row["birth_month"] == 2
                and now.month == 2
                and now.day == 28
            ):
                try:
                    date(now.year, 2, 29)
                except ValueError:
                    is_today = True

            if not is_today:
                continue

            if not force and await self.db.was_sent(
                guild.id, row["user_id"], birthday_key
            ):
                continue

            mention = f"<@{row['user_id']}>"
            age = None
            if row["birth_year"]:
                age = now.year - row["birth_year"]

raw_message = settings["announcement_message"]

templates = [
    item.strip()
    for item in re.split(r"\s*(?:\||\n+)\s*", raw_message)
    if item.strip()
]

if not templates:
    templates = [
        "🎂 Сегодня день рождения у {mention}! Поздравляем! 🎉"
    ]

message_template = random.choice(templates)

message = message_template.format(
    mention=mention,
    user_id=row["user_id"],
    age=age if age is not None else "",
)

            embed = discord.Embed(
                title="🎉 День рождения!",
                description=message,
                timestamp=now,
            )
            if age is not None and age >= 0:
                embed.add_field(name="Исполнилось", value=f"{age}", inline=True)

            await channel.send(
                content=mention,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=True, roles=False, everyone=False
                ),
            )
            if not force:
                await self.db.mark_sent(guild.id, row["user_id"], birthday_key)
            sent_count += 1

        return sent_count


class BirthdayCommands(
    app_commands.Group,
    name="birthday",
    description="Управление своей датой рождения",
):
    def __init__(self, bot: BirthdayBot):
        super().__init__()
        self.bot = bot

    @app_commands.command(name="set", description="Добавить или изменить свой день рождения")
    @app_commands.describe(
        day="День месяца",
        month="Номер месяца от 1 до 12",
        year="Год рождения — необязательно",
    )
    @app_commands.guild_only()
    async def set_birthday(
        self,
        interaction: discord.Interaction,
        day: app_commands.Range[int, 1, 31],
        month: app_commands.Range[int, 1, 12],
        year: Optional[app_commands.Range[int, 1900, 2100]] = None,
    ) -> None:
        assert interaction.guild_id is not None

        if not validate_date(day, month, year):
            await interaction.response.send_message(
                "Такой даты не существует.", ephemeral=True
            )
            return

        await self.bot.db.set_birthday(
            interaction.guild_id,
            interaction.user.id,
            day,
            month,
            year,
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"Дата сохранена: **{format_birthday(day, month, year)}**.",
            ephemeral=True,
        )

    @app_commands.command(name="view", description="Посмотреть сохранённую дату")
    @app_commands.guild_only()
    async def view(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        row = await self.bot.db.get_birthday(
            interaction.guild_id, interaction.user.id
        )
        if not row:
            await interaction.response.send_message(
                "У тебя пока не сохранён день рождения.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Твоя дата: **{format_birthday(row['birth_day'], row['birth_month'], row['birth_year'])}**.",
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Удалить свою дату рождения")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        removed = await self.bot.db.remove_birthday(
            interaction.guild_id, interaction.user.id
        )
        text = "Дата рождения удалена." if removed else "Сохранённой даты не было."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="upcoming", description="Показать ближайшие дни рождения")
    @app_commands.describe(limit="Количество записей от 1 до 20")
    @app_commands.guild_only()
    async def upcoming(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        assert interaction.guild_id is not None
        settings = await self.bot.db.get_settings(interaction.guild_id)

        try:
            today = datetime.now(ZoneInfo(settings["timezone"])).date()
        except ZoneInfoNotFoundError:
            today = datetime.now().date()

        rows = await self.bot.db.get_birthdays(interaction.guild_id)
        if not rows:
            await interaction.response.send_message(
                "На сервере пока нет сохранённых дней рождения.",
                ephemeral=True,
            )
            return

        sorted_rows = sorted(
            rows,
            key=lambda row: next_birthday(
                row["birth_day"], row["birth_month"], today
            ),
        )[:limit]

        lines = []
        for row in sorted_rows:
            upcoming_date = next_birthday(
                row["birth_day"], row["birth_month"], today
            )
            days_left = (upcoming_date - today).days
            suffix = "сегодня" if days_left == 0 else f"через {days_left} дн."
            lines.append(
                f"<@{row['user_id']}> — "
                f"**{format_birthday(row['birth_day'], row['birth_month'], None)}** "
                f"({suffix})"
            )

        embed = discord.Embed(
            title="🎂 Ближайшие дни рождения",
            description="\n".join(lines),
        )
        await interaction.response.send_message(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class BirthdayAdminCommands(
    app_commands.Group,
    name="birthday-admin",
    description="Настройки дней рождения для администраторов",
):
    def __init__(self, bot: BirthdayBot):
        super().__init__()
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Команда доступна только на сервере.", ephemeral=True
            )
            return False

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Нужно разрешение **Управлять сервером**.", ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="set", description="Добавить дату другому участнику")
    @app_commands.describe(
        member="Участник сервера",
        day="День месяца",
        month="Номер месяца",
        year="Год рождения — необязательно",
    )
    @app_commands.guild_only()
    async def set_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        day: app_commands.Range[int, 1, 31],
        month: app_commands.Range[int, 1, 12],
        year: Optional[app_commands.Range[int, 1900, 2100]] = None,
    ) -> None:
        assert interaction.guild_id is not None
        if not validate_date(day, month, year):
            await interaction.response.send_message(
                "Такой даты не существует.", ephemeral=True
            )
            return

        await self.bot.db.set_birthday(
            interaction.guild_id,
            member.id,
            day,
            month,
            year,
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"Для {member.mention} сохранено: "
            f"**{format_birthday(day, month, year)}**.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="remove", description="Удалить дату другого участника")
    @app_commands.guild_only()
    async def remove_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        assert interaction.guild_id is not None
        removed = await self.bot.db.remove_birthday(
            interaction.guild_id, member.id
        )
        text = (
            f"Дата {member.mention} удалена."
            if removed
            else f"У {member.mention} не было сохранённой даты."
        )
        await interaction.response.send_message(
            text,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="channel", description="Выбрать канал поздравлений")
    @app_commands.guild_only()
    async def channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild_id is not None

        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            await interaction.response.send_message(
                "У бота в этом канале должны быть права **Отправлять сообщения** "
                "и **Встраивать ссылки**.",
                ephemeral=True,
            )
            return

        await self.bot.db.set_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"Канал поздравлений: {channel.mention}.", ephemeral=True
        )

    @app_commands.command(name="timezone", description="Установить часовой пояс сервера")
    @app_commands.describe(name="Например: Asia/Almaty, Europe/Moscow")
    @app_commands.guild_only()
    async def timezone(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        assert interaction.guild_id is not None
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError:
            await interaction.response.send_message(
                "Часовой пояс не найден. Пример: `Asia/Almaty`.",
                ephemeral=True,
            )
            return

        await self.bot.db.set_timezone(interaction.guild_id, name)
        await interaction.response.send_message(
            f"Часовой пояс установлен: `{name}`.", ephemeral=True
        )

    @app_commands.command(name="hour", description="Установить час отправки поздравлений")
    @app_commands.describe(hour="Час от 0 до 23 по часовому поясу сервера")
    @app_commands.guild_only()
    async def hour(
        self,
        interaction: discord.Interaction,
        hour: app_commands.Range[int, 0, 23],
    ) -> None:
        assert interaction.guild_id is not None
        await self.bot.db.set_hour(interaction.guild_id, hour)
        await interaction.response.send_message(
            f"Поздравления будут отправляться после **{hour:02d}:00**.",
            ephemeral=True,
        )

    @app_commands.command(name="message", description="Изменить текст поздравления")
    @app_commands.describe(
        text="Можно использовать {mention}, {user_id} и {age}"
    )
    @app_commands.guild_only()
    async def message(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 1500],
    ) -> None:
        assert interaction.guild_id is not None

        try:
            text.format(mention="@user", user_id="123", age="20")
        except (KeyError, ValueError):
            await interaction.response.send_message(
                "В тексте есть неизвестный или повреждённый шаблон. "
                "Разрешены `{mention}`, `{user_id}`, `{age}`.",
                ephemeral=True,
            )
            return

        await self.bot.db.set_message(interaction.guild_id, text)
        await interaction.response.send_message(
            "Текст поздравления обновлён.", ephemeral=True
        )

    @app_commands.command(name="settings", description="Показать настройки сервера")
    @app_commands.guild_only()
    async def settings(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        row = await self.bot.db.get_settings(interaction.guild_id)
        channel_text = (
            f"<#{row['announcement_channel_id']}>"
            if row["announcement_channel_id"]
            else "не выбран"
        )
        embed = discord.Embed(title="⚙️ Настройки Birthday Bot")
        embed.add_field(name="Канал", value=channel_text, inline=False)
        embed.add_field(name="Часовой пояс", value=row["timezone"], inline=True)
        embed.add_field(
            name="Время", value=f"{row['announcement_hour']:02d}:00", inline=True
        )
        embed.add_field(
            name="Сообщение", value=row["announcement_message"], inline=False
        )
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="test",
        description="Отправить тестовое поздравление для сегодняшних именинников",
    )
    @app_commands.guild_only()
    async def test(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        count = await self.bot.process_guild_birthdays(
            interaction.guild, force=True
        )
        if count:
            await interaction.followup.send(
                f"Отправлено тестовых поздравлений: **{count}**.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Сегодня нет сохранённых именинников либо канал ещё не настроен. "
                "Для проверки временно поставь кому-нибудь сегодняшнюю дату.",
                ephemeral=True,
            )


async def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is missing. Copy .env.example to .env and add the bot token."
        )

    bot = BirthdayBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
