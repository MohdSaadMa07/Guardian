import os
import psutil
import time

CORE_COUNT = os.cpu_count() or 1
SKIP_PROCESSES = {'System Idle Process', 'Idle'}

# Baseline for calculating per-second network speed
_last_net = psutil.net_io_counters()
_last_net_time = time.time()


class SystemStats:
    def __init__(self, cpu: float, ram: float, disk: float = 0,
                 processes: int = 0, ram_mb: float = 0, ram_total_mb: float = 0,
                 disk_free_gb: float = 0, disk_total_gb: float = 0,
                 net_sent_mb: float = 0, net_recv_mb: float = 0,
                 net_sent_speed: float = 0, net_recv_speed: float = 0):
        self.cpu = cpu
        self.ram = ram
        self.disk = disk
        self.processes = processes
        self.ram_mb = ram_mb
        self.ram_total_mb = ram_total_mb
        self.disk_free_gb = disk_free_gb
        self.disk_total_gb = disk_total_gb
        self.net_sent_mb = net_sent_mb        # total MB sent since boot
        self.net_recv_mb = net_recv_mb        # total MB received since boot
        self.net_sent_speed = net_sent_speed  # KB/s upload
        self.net_recv_speed = net_recv_speed  # KB/s download

    def get_ram_available_mb(self) -> float:
        return self.ram_total_mb - self.ram_mb


def get_process_snapshot(limit: int = 8):
    processes = []

    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'create_time']):
        try:
            p = proc.info

            if p['name'] in SKIP_PROCESSES:
                continue

            processes.append({
                "pid":    p['pid'],
                "name":   p['name'],
                "cpu":    round(p['cpu_percent'] / CORE_COUNT, 1),
                "memory": round(p['memory_percent'], 1),
                "uptime": time.time() - p['create_time'],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    processes.sort(key=lambda x: x['cpu'], reverse=True)
    return processes[:limit]


def get_net_speed():
    """Returns (sent_kb_per_s, recv_kb_per_s) since last call."""
    global _last_net, _last_net_time

    now     = time.time()
    current = psutil.net_io_counters()
    elapsed = now - _last_net_time or 1.0

    sent_speed = (current.bytes_sent - _last_net.bytes_sent) / elapsed / 1024
    recv_speed = (current.bytes_recv - _last_net.bytes_recv) / elapsed / 1024

    _last_net      = current
    _last_net_time = now

    return max(0, sent_speed), max(0, recv_speed)


def get_stats() -> SystemStats:
    try:
        cpu = psutil.cpu_percent(interval=0.1)

        ram_info      = psutil.virtual_memory()
        ram           = ram_info.percent
        ram_mb        = ram_info.used  / (1024 ** 2)
        ram_total_mb  = ram_info.total / (1024 ** 2)

        disk_info     = psutil.disk_usage('/')
        disk          = disk_info.percent
        disk_free_gb  = disk_info.free  / (1024 ** 3)
        disk_total_gb = disk_info.total / (1024 ** 3)

        processes = len(psutil.pids())

        net           = psutil.net_io_counters()
        net_sent_mb   = net.bytes_sent / (1024 ** 2)
        net_recv_mb   = net.bytes_recv / (1024 ** 2)
        sent_speed, recv_speed = get_net_speed()

        return SystemStats(
            cpu=cpu, ram=ram, disk=disk,
            processes=processes,
            ram_mb=ram_mb, ram_total_mb=ram_total_mb,
            disk_free_gb=disk_free_gb, disk_total_gb=disk_total_gb,
            net_sent_mb=net_sent_mb, net_recv_mb=net_recv_mb,
            net_sent_speed=sent_speed, net_recv_speed=recv_speed,
        )

    except Exception as e:
        print(f"[ERROR] Failed to collect stats: {e}")
        return SystemStats(
            cpu=0, ram=0, disk=0, processes=0,
            ram_mb=0, ram_total_mb=0,
            disk_free_gb=0, disk_total_gb=0,
        )