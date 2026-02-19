import time
from collections import deque
from datetime import datetime

from rich import box
from rich.align import Align
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from db import get_stats_summary, init_db, save
from monitor import get_process_snapshot, get_stats

init_db()

# ── Config ────────────────────────────────────────────────────────────────────

THRESHOLDS = {
    "cpu":  {"warning": 60, "critical": 85},
    "ram":  {"warning": 70, "critical": 85},
    "disk": {"warning": 70, "critical": 90},
}

SPARKLINE_LEN  = 24
SPARKLINE_BARS = " ▁▂▃▄▅▆▇█"
REFRESH_RATE   = 1
START_TIME     = datetime.now()

cpu_history  = deque([0.0] * SPARKLINE_LEN, maxlen=SPARKLINE_LEN)
ram_history  = deque([0.0] * SPARKLINE_LEN, maxlen=SPARKLINE_LEN)
disk_history = deque([0.0] * SPARKLINE_LEN, maxlen=SPARKLINE_LEN)
net_up_history   = deque([0.0] * SPARKLINE_LEN, maxlen=SPARKLINE_LEN)
net_down_history = deque([0.0] * SPARKLINE_LEN, maxlen=SPARKLINE_LEN)
alert_log    = deque(maxlen=5)

# Track last alert time per metric to avoid spam
_last_alert_time = {}
ALERT_COOLDOWN = 60  # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _threshold(value: float, metric: str):
    t = THRESHOLDS.get(metric, {"warning": 70, "critical": 85})
    if value >= t["critical"]:
        return "red", "CRITICAL", "bold red"
    if value >= t["warning"]:
        return "yellow", "WARNING", "bold yellow"
    return "green", "NORMAL", "bold green"


def _sparkline(history: deque, color: str) -> Text:
    spark = Text()
    for v in history:
        idx = int(v / 100 * (len(SPARKLINE_BARS) - 1))
        idx = max(0, min(idx, len(SPARKLINE_BARS) - 1))
        spark.append(SPARKLINE_BARS[idx], style=color)
    return spark


def _net_sparkline(history: deque, color: str, peak: float) -> Text:
    spark = Text()
    denom = peak if peak > 0 else 1
    for v in history:
        idx = int(v / denom * (len(SPARKLINE_BARS) - 1))
        idx = max(0, min(idx, len(SPARKLINE_BARS) - 1))
        spark.append(SPARKLINE_BARS[idx], style=color)
    return spark


def _bar(value: float, metric: str, width: int = 24) -> Text:
    color, _, _ = _threshold(value, metric)
    filled = int(value / 100 * width)
    bar = Text()
    bar.append("█" * filled,           style=color)
    bar.append("░" * (width - filled), style="grey23")
    return bar


def _mini_bar(value: float, color: str, width: int = 16) -> Text:
    filled = int(min(value, 100) / 100 * width)
    bar = Text()
    bar.append("█" * filled,           style=color)
    bar.append("░" * (width - filled), style="grey23")
    return bar


def _fmt_speed(kb: float) -> str:
    if kb >= 1024:
        return f"{kb/1024:.1f} MB/s"
    return f"{kb:.0f} KB/s"


def _fmt_total(mb: float) -> str:
    if mb >= 1024:
        return f"{mb/1024:.2f} GB"
    return f"{mb:.0f} MB"


def _uptime() -> str:
    delta = datetime.now() - START_TIME
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _log_alert(key: str, msg: str):
    now = time.time()
    if now - _last_alert_time.get(key, 0) < ALERT_COOLDOWN:
        return
    _last_alert_time[key] = now
    ts = datetime.now().strftime("%H:%M:%S")
    alert_log.appendleft(f"[dim]{ts}[/dim]  {msg}")


# ── Panels ────────────────────────────────────────────────────────────────────

def build_header() -> Panel:
    now = datetime.now().strftime("%A, %d %b %Y  %H:%M:%S")
    return Panel(
        Align(
            Group(
                Text("⬡  GUARDIAN SYSTEM MONITOR", style="bold cyan", justify="center"),
                Text(f"  {now}   ·   uptime {_uptime()}", style="dim", justify="center"),
            ),
            align="center",
        ),
        style="cyan",
        box=box.DOUBLE_EDGE,
        padding=(0, 2),
    )


def build_metrics(stats) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(width=12)
    grid.add_column(width=7,  justify="right")
    grid.add_column(width=24)
    grid.add_column(width=10, justify="center")

    def metric_row(label, value, metric, history):
        color, status, badge_style = _threshold(value, metric)
        grid.add_row(
            Text(label, style="dim"),
            Text(f"{value:.1f}%", style=f"bold {color}"),
            _bar(value, metric, 24),
            Text(f" {status} ", style=f"{badge_style} on grey7"),
        )
        grid.add_row("", "", _sparkline(history, color), "")

    metric_row("CPU Usage",  stats.cpu,  "cpu",  cpu_history)
    metric_row("RAM Usage",  stats.ram,  "ram",  ram_history)
    metric_row("Disk Usage", stats.disk, "disk", disk_history)

    grid.add_row(
        Text("RAM Used",  style="dim"),
        Text(f"{stats.ram_mb/1024:.1f} GB", style="cyan"),
        Text(f"of {stats.ram_total_mb/1024:.1f} GB total", style="dim"), "",
    )
    grid.add_row(
        Text("Disk Free",  style="dim"),
        Text(f"{stats.disk_free_gb:.0f} GB", style="cyan"),
        Text(f"of {stats.disk_total_gb:.0f} GB total", style="dim"), "",
    )
    grid.add_row(
        Text("Processes", style="dim"),
        Text(str(stats.processes), style="bold white"), "", "",
    )

    return Panel(grid, title="[bold cyan]  Metrics[/]", border_style="cyan", box=box.ROUNDED)


def build_processes(procs) -> Panel:
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold magenta",
        show_edge=False,
        pad_edge=False,
        expand=True,
    )
    table.add_column("Process", min_width=16, no_wrap=True)
    table.add_column("PID",  width=6,  justify="right", style="dim")
    table.add_column("CPU%", width=6,  justify="right")
    table.add_column("",     width=16)
    table.add_column("RAM%", width=6,  justify="right")
    table.add_column("",     width=16)

    for p in procs:
        cpu_v = float(p["cpu"])
        ram_v = float(p["memory"])

        cpu_color = "red" if cpu_v > 70 else "yellow" if cpu_v > 40 else "green"
        ram_color = "red" if ram_v > 20 else "yellow" if ram_v > 10 else "cyan"

        table.add_row(
            Text(p["name"][:18], style="bold white"),
            Text(str(p["pid"])),
            Text(f"{cpu_v:.1f}%", style=f"bold {cpu_color}"),
            _mini_bar(cpu_v, cpu_color, 16),
            Text(f"{ram_v:.1f}%", style=f"bold {ram_color}"),
            _mini_bar(ram_v * 5, ram_color, 16),
        )

    return Panel(
        table,
        title="[bold magenta]  Top Processes[/]",
        border_style="magenta",
        box=box.ROUNDED,
    )


def build_status(stats) -> Panel:
    checks = [
        (stats.cpu,  "cpu",  "CPU"),
        (stats.ram,  "ram",  "RAM"),
        (stats.disk, "disk", "Disk"),
    ]
    fired = []
    for val, metric, label in checks:
        _, status, style = _threshold(val, metric)
        if status != "NORMAL":
            msg = f"[{style}]{label} {status}[/] — {val:.1f}%"
            fired.append(msg)
            _log_alert(metric, f"{label} {status} — {val:.1f}%")

    if not fired:
        body   = Text("✔  All systems nominal", style="bold green")
        border = "green"
    else:
        body   = Text("\n").join(Text.from_markup(f) for f in fired)
        border = "red"

    return Panel(body, title="[bold]  Status[/]", border_style=border, box=box.ROUNDED)


def build_network(stats) -> Panel:
    up_kb   = stats.net_sent_speed
    down_kb = stats.net_recv_speed
    peak_up   = max(net_up_history)   or 1
    peak_down = max(net_down_history) or 1

    up_color   = "yellow" if up_kb   > 1024 else "green"
    down_color = "yellow" if down_kb > 1024 else "cyan"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(width=6,  style="dim")
    grid.add_column(width=12, justify="right")
    grid.add_column(width=24)

    grid.add_row(
        Text("▲ UP",   style=f"bold {up_color}"),
        Text(_fmt_speed(up_kb),   style=f"bold {up_color}"),
        _net_sparkline(net_up_history,   up_color,   peak_up),
    )
    grid.add_row(
        Text("▼ DOWN", style=f"bold {down_color}"),
        Text(_fmt_speed(down_kb), style=f"bold {down_color}"),
        _net_sparkline(net_down_history, down_color, peak_down),
    )

    grid.add_row("", "", "")   # spacer

    grid.add_row(
        Text("Sent",  style="dim"),
        Text(_fmt_total(stats.net_sent_mb), style="green"),
        Text("since boot", style="dim"),
    )
    grid.add_row(
        Text("Recv",  style="dim"),
        Text(_fmt_total(stats.net_recv_mb), style="cyan"),
        Text("since boot", style="dim"),
    )

    return Panel(grid, title="[bold green]  Network I/O[/]", border_style="green", box=box.ROUNDED)


def build_alert_log() -> Panel:
    if not alert_log:
        body = Text("No threshold events recorded.", style="dim italic")
    else:
        body = Text("\n").join(Text.from_markup(line) for line in alert_log)
    return Panel(body, title="[bold red]  Alert Log[/]", border_style="red", box=box.ROUNDED)


# ── Layout ────────────────────────────────────────────────────────────────────

def make_layout(stats, procs) -> Layout:
    root = Layout()

    root.split_column(
        Layout(name="header",    size=4),
        Layout(name="body"),
        Layout(name="alert_log", size=7),
    )

    root["body"].split_row(
        Layout(name="left",  ratio=2),
        Layout(name="right", ratio=3),
    )

    root["right"].split_column(
        Layout(name="processes",  ratio=3),
        Layout(name="bottom_row", ratio=2),
    )

    root["bottom_row"].split_row(
        Layout(name="status"),
        Layout(name="network"),
    )

    root["header"].update(build_header())
    root["left"].update(build_metrics(stats))
    root["processes"].update(build_processes(procs))
    root["status"].update(build_status(stats))
    root["network"].update(build_network(stats))
    root["alert_log"].update(build_alert_log())

    return root


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        with Live(auto_refresh=False, screen=True) as live:
            while True:
                stats = get_stats()
                procs = get_process_snapshot()
                save(stats.cpu, stats.ram)

                cpu_history.append(stats.cpu)
                ram_history.append(stats.ram)
                disk_history.append(stats.disk)
                net_up_history.append(stats.net_sent_speed)
                net_down_history.append(stats.net_recv_speed)

                live.update(make_layout(stats, procs), refresh=True)
                time.sleep(REFRESH_RATE)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()