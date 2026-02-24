import io
import logging
import asyncio
import aiohttp
import qrcode

from src.config import (
    EVOLUTION_API_URL,
    EVOLUTION_API_KEY,
    EVOLUTION_INSTANCE,
    WHATSAPP_ALLOWED_NUMBERS,
)

log = logging.getLogger("monitor.whatsapp")

alert_numbers: set[str] = set()

WEBHOOK_EVENTS = [
    "QRCODE_UPDATED",
    "CONNECTION_UPDATE",
    "MESSAGES_UPSERT",
]


def _headers():
    return {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{EVOLUTION_API_URL}/{path}"


def _print_qr(code: str):
    qr = qrcode.QRCode(border=1)
    qr.add_data(code)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    print("\n  Escaneie o QR Code no WhatsApp > Aparelhos Conectados:")
    print()
    for line in buf.getvalue().splitlines():
        print(f"  {line}")
    print()


def is_allowed(number: str) -> bool:
    clean = number.replace("+", "").replace(" ", "").split("@")[0]
    return clean in WHATSAPP_ALLOWED_NUMBERS


async def create_instance() -> bool:
    async with aiohttp.ClientSession() as session:
        payload = {
            "instanceName": EVOLUTION_INSTANCE,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
            "rejectCall": True,
            "msgCall": "Nao posso atender no momento.",
            "groupsIgnore": True,
            "alwaysOnline": True,
            "readMessages": False,
            "readStatus": False,
            "syncFullHistory": False,
        }
        async with session.post(
            _url("instance/create"), headers=_headers(), json=payload
        ) as resp:
            data = await resp.json()
            if resp.status in (200, 201):
                log.info(f"Instancia '{EVOLUTION_INSTANCE}' criada")
                qr = data.get("qrcode", {})
                code = qr.get("code", "")
                if code:
                    _print_qr(code)
                return True
            if "already in use" in str(data) or "instance already" in str(data).lower():
                log.info(f"Instancia '{EVOLUTION_INSTANCE}' ja existe")
                return False
            log.warning(f"Criar instancia: {resp.status} {data}")
            return False


async def connect_instance() -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            _url(f"instance/connect/{EVOLUTION_INSTANCE}"), headers=_headers()
        ) as resp:
            data = await resp.json()
            code = data.get("code", "")
            pairing = data.get("pairingCode", "")
            if code:
                _print_qr(code)
            if pairing:
                log.info(f"Pairing code: {pairing}")
            if not code and not pairing:
                log.info(f"Connect response: {data}")
            return data


async def get_instance_status() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            _url(f"instance/connectionState/{EVOLUTION_INSTANCE}"), headers=_headers()
        ) as resp:
            data = await resp.json()
            return data.get("instance", {}).get("state", "unknown")


async def setup_webhook(url: str):
    async with aiohttp.ClientSession() as session:
        payload = {
            "webhook": {
                "enabled": True,
                "url": url,
                "webhookByEvents": False,
                "webhookBase64": False,
                "events": WEBHOOK_EVENTS,
            },
        }
        async with session.post(
            _url(f"webhook/set/{EVOLUTION_INSTANCE}"),
            headers=_headers(),
            json=payload,
        ) as resp:
            if resp.status in (200, 201):
                log.info(f"Webhook configurado: {url}")
            else:
                data = await resp.json()
                log.error(f"Erro ao configurar webhook: {resp.status} {data}")


async def wait_for_qrcode() -> str | None:
    for attempt in range(10):
        data = await connect_instance()
        code = data.get("code", "")
        if code:
            return code
        await asyncio.sleep(3)
    log.warning("QR code nao gerado apos 10 tentativas")
    return None


async def send_text(number: str, text: str) -> bool:
    async with aiohttp.ClientSession() as session:
        payload = {"number": number, "text": text}
        async with session.post(
            _url(f"message/sendText/{EVOLUTION_INSTANCE}"),
            headers=_headers(),
            json=payload,
        ) as resp:
            if resp.status in (200, 201):
                return True
            data = await resp.json()
            log.error(f"Erro ao enviar texto para {number}: {resp.status} {data}")
            return False



async def send_alert(text: str):
    for number in alert_numbers:
        await send_text(number, text)
