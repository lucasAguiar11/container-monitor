import os

CONTAINERS = os.environ.get("CONTAINERS", "portal").split(",")
CPU_LIMIT = float(os.environ.get("CPU_LIMIT", 50))
MEM_LIMIT = float(os.environ.get("MEM_LIMIT", 70))
INTERVALO = int(os.environ.get("INTERVALO", 30))
COOLDOWN = int(os.environ.get("COOLDOWN", 300))

EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL", "http://evolution-api:8080")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE", "container-monitor")
WHATSAPP_ALLOWED_NUMBERS = [
    n.strip() for n in os.environ.get("WHATSAPP_ALLOWED_NUMBERS", "").split(",") if n.strip()
]
