import psutil
import time
from typing import Tuple


class SystemStats:
    def __init__(self, cpu: float, ram: float, disk: float = 0,
                 processes: int = 0, ram_mb: float = 0, ram_total_mb: float = 0,
                 disk_free_gb: float = 0, disk_total_gb: float = 0):
        self.cpu = cpu
        self.ram = ram
        self.disk = disk
        self.processes = processes
        self.ram_mb = ram_mb
        self.ram_total_mb = ram_total_mb
        self.disk_free_gb = disk_free_gb
        self.disk_total_gb = disk_total_gb

    def get_ram_available_mb(self) -> float:
        return self.ram_total_mb - self.ram_mb


def get_process_snapshot(limit=10):
    processes = []

    for proc in psutil.process_iter(['pid','name','cpu_percent','memory_percent','create_time']):
        try:
            p = proc.info
            processes.append({
                "pid": p['pid'],
                "name": p['name'],
                "cpu": p['cpu_percent'],
                "memory": p['memory_percent'],
                "uptime": time.time() - p['create_time']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    processes.sort(key=lambda x: x['cpu'], reverse=True)
    return processes[:limit]

def get_stats() -> SystemStats:
    try:
        cpu = psutil.cpu_percent(interval=0.1)

        ram_info = psutil.virtual_memory()
        ram = ram_info.percent
        ram_mb = ram_info.used / (1024 * 1024)
        ram_total_mb = ram_info.total / (1024 * 1024)

        disk_info = psutil.disk_usage('/')
        disk = disk_info.percent
        disk_free_gb = disk_info.free / (1024 * 1024 * 1024)
        disk_total_gb = disk_info.total / (1024 * 1024 * 1024)

        processes = len(psutil.pids())

        return SystemStats(
            cpu=cpu,
            ram=ram,
            disk=disk,
            processes=processes,
            ram_mb=ram_mb,
            ram_total_mb=ram_total_mb,
            disk_free_gb=disk_free_gb,
            disk_total_gb=disk_total_gb
        )

    except Exception as e:
        print(f"[ERROR] Failed to collect stats: {e}")
        return SystemStats(
            cpu=0, ram=0, disk=0,
            processes=0, ram_mb=0, ram_total_mb=0,
            disk_free_gb=0, disk_total_gb=0
        )