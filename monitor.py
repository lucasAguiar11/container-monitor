import os
import asyncio
import time
import logging
import docker
import psutil
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("monitor")

TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USERS = [int(uid) for uid in os.environ["ALLOWED_USERS"].split(",")]
CONTAINERS = os.environ.get("CONTAINERS", "portal").split(",")
CPU_LIMIT = float(os.environ.get("CPU_LIMIT", 50))
MEM_LIMIT = float(os.environ.get("MEM_LIMIT", 70))
INTERVALO = int(os.environ.get("INTERVALO", 30))
COOLDOWN = int(os.environ.get("COOLDOWN", 300))

client = docker.from_env()
alert_chat_ids: set[int] = set()
last_alerts: dict[str, float] = {}
container_down: dict[str, bool] = {}


def host_usage() -> str:
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return (
        f"CPU: {cpu}% | "
        f"MEM: {mem.percent}% ({mem.used // 1024 // 1024}MB / {mem.total // 1024 // 1024}MB) | "
        f"Disco: {disk.percent}% ({disk.used // 1024 // 1024 // 1024}GB / {disk.total // 1024 // 1024 // 1024}GB)"
    )


def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS


def get_stats(name: str) -> dict | None:
    try:
        c = client.containers.get(name)
        if c.status != "running":
            log.warning(f"Container {name} nao esta running (status={c.status})")
            return None
        stats = c.stats(stream=False)
        cpu_delta = (
            stats["cpu_stats"]["cpu_usage"]["total_usage"]
            - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = (
            stats["cpu_stats"]["system_cpu_usage"]
            - stats["precpu_stats"]["system_cpu_usage"]
        )
        cpu_count = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))
        cpu_percent = (cpu_delta / system_delta) * cpu_count * 100 if system_delta > 0 else 0
        mem_usage = stats["memory_stats"]["usage"]
        mem_limit = stats["memory_stats"]["limit"]
        mem_percent = (mem_usage / mem_limit) * 100
        return {
            "cpu": round(cpu_percent, 2),
            "mem": round(mem_percent, 2),
            "mem_usage": f"{mem_usage // 1024 // 1024}MB / {mem_limit // 1024 // 1024}MB",
            "status": "running",
        }
    except Exception as e:
        log.error(f"Erro ao obter stats de {name}: {e}")
        return None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"/start de {user.full_name} (@{user.username}, id={user.id})")
    if not is_allowed(user.id):
        log.warning(f"Acesso negado para {user.id}")
        await update.message.reply_text("Sem permissao.")
        return
    alert_chat_ids.add(update.effective_chat.id)
    await update.message.reply_text(
        f"Monitoramento ativo!\n"
        f"Containers: {', '.join(CONTAINERS)}\n"
        f"CPU > {CPU_LIMIT}% | MEM > {MEM_LIMIT}%\n"
        f"Checando a cada {INTERVALO}s"
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"/stop de {user.full_name} (@{user.username}, id={user.id})")
    if not is_allowed(user.id):
        return
    alert_chat_ids.discard(update.effective_chat.id)
    await update.message.reply_text("Monitoramento pausado.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"/status de {user.full_name} (@{user.username}, id={user.id})")
    if not is_allowed(user.id):
        return
    lines = []
    for name in CONTAINERS:
        stats = get_stats(name)
        if stats:
            lines.append(
                f"*{name}*\n"
                f"   CPU: {stats['cpu']}% | MEM: {stats['mem']}% ({stats['mem_usage']})"
            )
        else:
            lines.append(f"*{name}* — parado ou nao encontrado")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"/id de {user.full_name} (@{user.username}, id={user.id})")
    await update.message.reply_text(
        f"*User ID:* `{user.id}`\n"
        f"*Nome:* {user.full_name}\n"
        f"*Username:* @{user.username}\n"
        f"*Chat ID:* `{update.effective_chat.id}`",
        parse_mode="Markdown",
    )


async def monitor_loop(app: Application):
    while True:
        if alert_chat_ids:
            now = time.time()
            for name in CONTAINERS:
                stats = get_stats(name)

                if stats is None:
                    if not container_down.get(name) and now - last_alerts.get(name, 0) >= COOLDOWN:
                        usage = host_usage()
                        log.warning(f"ALERTA: container {name} caiu! | {usage}")
                        for chat_id in alert_chat_ids:
                            await app.bot.send_message(
                                chat_id,
                                f"*{name}* caiu!\n\n`{usage}`",
                                parse_mode="Markdown",
                            )
                        last_alerts[name] = now
                        container_down[name] = True
                else:
                    if container_down.get(name):
                        usage = host_usage()
                        log.info(f"Container {name} voltou | {usage}")
                        for chat_id in alert_chat_ids:
                            await app.bot.send_message(
                                chat_id,
                                f"*{name}* voltou!\n\n`{usage}`",
                                parse_mode="Markdown",
                            )
                        container_down[name] = False

                    msg = ""
                    if stats["cpu"] > CPU_LIMIT:
                        msg += f"*{name}* — CPU em *{stats['cpu']}%*\n"
                    if stats["mem"] > MEM_LIMIT:
                        msg += f"*{name}* — MEM em *{stats['mem']}%* ({stats['mem_usage']})\n"

                    if msg and now - last_alerts.get(name, 0) >= COOLDOWN:
                        log.warning(f"ALERTA: {name} CPU={stats['cpu']}% MEM={stats['mem']}%")
                        for chat_id in alert_chat_ids:
                            await app.bot.send_message(chat_id, msg, parse_mode="Markdown")
                        last_alerts[name] = now

        await asyncio.sleep(INTERVALO)


async def post_init(app: Application):
    log.info(f"Bot iniciado | Containers: {CONTAINERS} | CPU>{CPU_LIMIT}% MEM>{MEM_LIMIT}% | Intervalo: {INTERVALO}s")
    await app.bot.set_my_commands([
        BotCommand("start", "Ativar monitoramento"),
        BotCommand("stop", "Pausar monitoramento"),
        BotCommand("status", "Ver status dos containers"),
        BotCommand("id", "Ver seu user ID"),
    ])
    asyncio.create_task(monitor_loop(app))


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("id", cmd_id))
    app.run_polling()


if __name__ == "__main__":
    main()
