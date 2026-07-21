# Discord Birthday Bot

Рабочий MVP бота дней рождения на Python.

## Возможности

- `/birthday set` — пользователь сохраняет свою дату.
- `/birthday view` — просматривает свою дату.
- `/birthday remove` — удаляет свою дату.
- `/birthday upcoming` — список ближайших дней рождения.
- `/birthday-admin set` — администратор добавляет дату другому участнику.
- `/birthday-admin remove` — администратор удаляет дату участника.
- `/birthday-admin channel` — назначает канал поздравлений.
- `/birthday-admin timezone` — задаёт часовой пояс.
- `/birthday-admin hour` — задаёт час отправки.
- `/birthday-admin message` — меняет текст поздравления.
- `/birthday-admin settings` — показывает настройки.
- `/birthday-admin test` — проверяет отправку без ожидания следующего дня.

Админские команды требуют разрешение Discord «Управлять сервером».

## 1. Требования

- Python 3.11 или новее.
- Discord-сервер, на котором у вас есть право управлять сервером.

Проверка Python:

```bash
python3 --version
```


## 2. Создание приложения в Discord

1. Откройте Discord Developer Portal.
2. Нажмите **New Application**.
3. Назовите приложение, например `Birthday Bot`.
4. Откройте раздел **Bot**.
5. Нажмите **Reset Token** и скопируйте токен.
6. Никому не отправляйте токен и не публикуйте файл `.env`.
7. В разделе **Installation** или **OAuth2 → URL Generator** выберите:
   - scope: `bot`;
   - scope: `applications.commands`;
   - права бота:
     - View Channels;
     - Send Messages;
     - Embed Links;
     - Read Message History.
8. Откройте созданную ссылку и добавьте бота на сервер.

Для этого проекта Message Content Intent не нужен.

## 3. Установка

### Windows PowerShell

```powershell
cd путь\к\discord_birthday_bot
```

Создайте виртуальное окружение:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Если PowerShell запрещает активацию:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Установите зависимости:

```powershell
python -m pip install -r requirements.txt
```

Создайте `.env`:

```powershell
Copy-Item .env.example .env
notepad .env
```

### Linux

```bash
cd /path/to/discord_birthday_bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
```

## 4. Настройка `.env`

```env
DISCORD_TOKEN=сюда_токен_бота
DEFAULT_TIMEZONE=ваша_зона
DATABASE_PATH=data/birthdays.db
DEV_GUILD_ID=
```

### Быстрое появление slash-команд

Глобальные команды Discord иногда появляются не моментально. Для разработки можно указать ID сервера:

1. Discord → Настройки пользователя → Расширенные → включить **Режим разработчика**.
2. Нажать правой кнопкой на значок сервера → **Копировать ID сервера**.
3. Вставить значение:

```env
DEV_GUILD_ID=123456789012345678
```

После завершения разработки удалите значение `DEV_GUILD_ID`, перезапустите бота и выполнится глобальная синхронизация команд.

## 5. Запуск

```bash
python bot.py
```

Успешный запуск выглядит примерно так:

```text
Logged in as Birthday Bot (...)
```

Не закрывайте окно терминала, пока бот должен работать.

## 6. Первичная настройка на сервере

В Discord выполните:

```text
/birthday-admin channel
```

Выберите канал поздравлений.

Затем:

```text
/birthday-admin timezone name:Asia/Almaty
/birthday-admin hour hour:9
```

Добавьте тестовую дату себе:

```text
/birthday set
```

Выберите сегодняшние день и месяц. После этого:

```text
/birthday-admin test
```

Бот должен отправить сообщение в настроенный канал.

## 7. Постоянная работа

Для работы 24/7 бот должен постоянно выполняться на:

- VPS;
- домашнем компьютере, который не выключается;
- Docker-хостинге;
- облачном сервисе с поддержкой постоянных Python-процессов.

SQLite подходит для одного процесса бота. Не запускайте две копии одновременно с одной и той же базой.

## Безопасность

- Упоминания `@everyone` и ролей отключены программно.
