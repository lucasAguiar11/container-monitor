import asyncio
import time
import logging
from aiohttp import web

from src import config
from src import monitor
from src import whatsapp as wa

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("monitor")


async def monitor_loop():
    while True:
        if wa.alert_numbers:
            now = time.time()
            for name in config.CONTAINERS:
                stats = monitor.get_stats(name)

                if stats is None:
                    if not monitor.container_down.get(name) and now - monitor.last_alerts.get(name, 0) >= config.COOLDOWN:
                        usage = monitor.host_usage()
                        log.warning(f"ALERTA: container {name} caiu! | {usage}")
                        await wa.send_alert(f"{name} caiu!\n\n{usage}")
                        monitor.last_alerts[name] = now
                        monitor.container_down[name] = True
                else:
                    if monitor.container_down.get(name):
                        usage = monitor.host_usage()
                        log.info(f"Container {name} voltou | {usage}")
                        await wa.send_alert(f"{name} voltou!\n\n{usage}")
                        monitor.container_down[name] = False

                    msg = ""
                    if stats["cpu"] > config.CPU_LIMIT:
                        msg += f"{name} — CPU em {stats['cpu']}%\n"
                    if stats["mem"] > config.MEM_LIMIT:
                        msg += f"{name} — MEM em {stats['mem']}% ({stats['mem_usage']})\n"

                    if msg and now - monitor.last_alerts.get(name, 0) >= config.COOLDOWN:
                        log.warning(f"ALERTA: {name} CPU={stats['cpu']}% MEM={stats['mem']}%")
                        await wa.send_alert(msg)
                        monitor.last_alerts[name] = now

        await asyncio.sleep(config.INTERVALO)


async def handle_webhook(request: web.Request) -> web.Response:
    data = await request.json()
    event = data.get("event")
    log.info(f"Webhook event: {event}")

    if event == "qrcode.updated":
        qr_data = data.get("data", {})
        qr_code = qr_data.get("qrcode", {}).get("code", "") or qr_data.get("code", "")
        pairing_code = qr_data.get("pairingCode", "")
        if qr_code:
            wa._print_qr(qr_code)
        if pairing_code:
            log.info(f"Pairing code: {pairing_code}")
        return web.Response(text="OK")

    if event == "connection.update":
        state = data.get("data", {}).get("state")
        log.info(f"WhatsApp connection: {state}")
        if state == "open":
            log.info("WhatsApp conectado com sucesso!")
        return web.Response(text="OK")

    if event == "messages.upsert":
        msg_data = data.get("data", {})
        key = msg_data.get("key", {})
        sender = key.get("remoteJid", "").split("@")[0]
        from_me = key.get("fromMe", False)
        text = msg_data.get("message", {}).get("conversation") or \
               msg_data.get("message", {}).get("extendedTextMessage", {}).get("text", "")

        if from_me or not text:
            return web.Response(text="OK")

        if not wa.is_allowed(sender):
            log.warning(f"Mensagem de numero nao permitido: {sender}")
            return web.Response(text="OK")

        log.info(f"WhatsApp de {sender}: {text}")
        cmd = text.strip().lower()

        if cmd in ("/start", "start", "iniciar"):
            wa.alert_numbers.add(sender)
            await wa.send_text(
                sender,
                f"Monitoramento ativo!\n"
                f"Containers: {', '.join(config.CONTAINERS)}\n"
                f"CPU > {config.CPU_LIMIT}% | MEM > {config.MEM_LIMIT}%\n"
                f"Checando a cada {config.INTERVALO}s",
            )

        elif cmd in ("/stop", "stop", "parar"):
            wa.alert_numbers.discard(sender)
            await wa.send_text(sender, "Monitoramento pausado.")

        elif cmd in ("/status", "status"):
            await wa.send_text(sender, monitor.format_status_plain())

        elif cmd in ("/help", "help", "ajuda", "menu"):
            active = "ON" if sender in wa.alert_numbers else "OFF"
            await wa.send_text(
                sender,
                f"*Container Monitor*\n"
                f"Alertas: {active}\n\n"
                f"*status* — ver containers agora\n"
                f"*start* — ativar alertas\n"
                f"*stop* — desativar alertas\n"
                f"*menu* — exibir este menu",
            )

        else:
            await wa.send_text(
                sender,
                "Comando nao reconhecido.\n\nDigite *menu* para ver as opcoes.",
            )

    return web.Response(text="OK")


async def start_app():
    log.info(
        f"Bot iniciado | Containers: {config.CONTAINERS} | "
        f"CPU>{config.CPU_LIMIT}% MEM>{config.MEM_LIMIT}% | Intervalo: {config.INTERVALO}s"
    )
    log.info(f"WhatsApp | Instancia: {config.EVOLUTION_INSTANCE} | Numeros permitidos: {config.WHATSAPP_ALLOWED_NUMBERS}")

    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 3000)
    await site.start()
    log.info("Webhook server rodando na porta 3000")

    webhook_url = "http://docker-monitor-bot:3000/webhook"

    for attempt in range(30):
        try:
            await wa.create_instance()
            await wa.setup_webhook(webhook_url)
            state = await wa.get_instance_status()
            log.info(f"Estado da instancia: {state}")
            if state != "open":
                await wa.wait_for_qrcode()
            break
        except Exception:
            log.info(f"Aguardando Evolution API... ({attempt + 1}/30)")
            await asyncio.sleep(5)

    asyncio.create_task(monitor_loop())

    await asyncio.Event().wait()


def main():
    asyncio.run(start_app())


if __name__ == "__main__":
    main()
