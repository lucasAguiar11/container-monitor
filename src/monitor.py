import logging
from typing import cast
import docker
import psutil

from src.config import CONTAINERS

log = logging.getLogger("monitor")
client = docker.from_env()

container_down: dict[str, bool] = {}
last_alerts: dict[str, float] = {}


def host_usage() -> str:
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return (
        f"CPU: {cpu}% | "
        f"MEM: {mem.percent}% ({mem.used // 1024 // 1024}MB / {mem.total // 1024 // 1024}MB) | "
        f"Disco: {disk.percent}% ({disk.used // 1024 // 1024 // 1024}GB / {disk.total // 1024 // 1024 // 1024}GB)"
    )


def get_stats(name: str) -> dict | None:
    try:
        c = client.containers.get(name)
        if c.status != "running":
            log.warning(f"Container {name} nao esta running (status={c.status})")
            return None
        stats = cast(dict, c.stats(stream=False))
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


def format_status_markdown() -> str:
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
    return "\n\n".join(lines)


def format_status_plain() -> str:
    lines = []
    for name in CONTAINERS:
        stats = get_stats(name)
        if stats:
            lines.append(f"{name}\n   CPU: {stats['cpu']}% | MEM: {stats['mem']}% ({stats['mem_usage']})")
        else:
            lines.append(f"{name} — parado ou nao encontrado")
    return "\n\n".join(lines)
