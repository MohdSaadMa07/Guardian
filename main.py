import time
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from monitor import get_process_snapshot, get_stats
from db import save, init_db, get_stats_summary

init_db()

THRESHOLDS = {
    'cpu': {'warning': 60, 'critical': 85},
    'ram': {'warning': 60, 'critical': 85},
    'disk': {'warning': 70, 'critical': 90}
}


def get_color(value: float, metric: str) -> str:
    thresholds = THRESHOLDS.get(metric, {'warning': 70, 'critical': 85})
    if value >= thresholds['critical']:
        return 'red'
    elif value >= thresholds['warning']:
        return 'yellow'
    return 'green'


def get_status_text(value: float, metric: str) -> str:
    thresholds = THRESHOLDS.get(metric, {'warning': 70, 'critical': 85})
    if value >= thresholds['critical']:
        return 'CRITICAL'
    elif value >= thresholds['warning']:
        return 'WARNING'
    return 'NORMAL'


def create_metrics_table(stats) -> Table:
    table = Table(title="Guardian System Monitor", show_header=True, header_style="bold cyan")
    table.add_column("Metric", width=20)
    table.add_column("Value", width=20)
    table.add_column("Status", width=15)

    table.add_row("CPU Usage",
                  f"[{get_color(stats.cpu,'cpu')}]{stats.cpu:.1f}%[/]",
                  get_status_text(stats.cpu,'cpu'))

    table.add_row("RAM Usage",
                  f"[{get_color(stats.ram,'ram')}]{stats.ram:.1f}%[/]",
                  get_status_text(stats.ram,'ram'))

    table.add_row("RAM Used", f"{stats.ram_mb:.0f} MB / {stats.ram_total_mb:.0f} MB", "")
    table.add_row("RAM Available", f"{stats.get_ram_available_mb():.0f} MB", "")

    table.add_row("Disk Usage",
                  f"[{get_color(stats.disk,'disk')}]{stats.disk:.1f}%[/]",
                  get_status_text(stats.disk,'disk'))

    table.add_row("Disk Free", f"{stats.disk_free_gb:.1f} GB / {stats.disk_total_gb:.1f} GB", "")
    table.add_row("Running Processes", str(stats.processes), "")

    return table


def create_alerts_panel(stats) -> Panel:
    alerts = []

    if stats.cpu >= THRESHOLDS['cpu']['critical']:
        alerts.append("CPU CRITICAL - System under heavy load")
    elif stats.cpu >= THRESHOLDS['cpu']['warning']:
        alerts.append("CPU WARNING - Performance may degrade")

    if stats.ram >= THRESHOLDS['ram']['critical']:
        alerts.append("RAM CRITICAL - Memory running low")
    elif stats.ram >= THRESHOLDS['ram']['warning']:
        alerts.append("RAM WARNING - Close unnecessary apps")

    if stats.disk >= THRESHOLDS['disk']['critical']:
        alerts.append("DISK CRITICAL - Storage almost full")
    elif stats.disk >= THRESHOLDS['disk']['warning']:
        alerts.append("DISK WARNING - Clean up storage")

    if not alerts:
        return Panel("System Status: All systems normal", title="Status", border_style="green")

    return Panel("\n".join(alerts), title="Alerts", border_style="red")


def create_summary_panel() -> Panel:
    s = get_stats_summary()

    text = f"""
Last Hour Statistics:
Samples: {s['samples']}
Avg CPU: {s['avg_cpu']:.1f}%
Avg RAM: {s['avg_ram']:.1f}%
Max CPU: {s['max_cpu']:.1f}%
Max RAM: {s['max_ram']:.1f}%
"""

    return Panel(text, title="Statistics", border_style="blue")


def create_process_panel(procs):
    if not procs:
        return Panel("No process data", title="Top Processes")

    text = "\n".join(
        f"{p['name']} (PID {p['pid']}) | CPU {p['cpu']}% | RAM {p['memory']:.1f}%"
        for p in procs
    )

    return Panel(text, title="Top Processes", border_style="magenta")


def make_layout(stats, procs) -> Layout:
    layout = Layout()

    layout.split_column(
        Layout(name="metrics", ratio=3),
        Layout(name="alerts", ratio=1),
        Layout(name="processes", ratio=2),
        Layout(name="summary", ratio=1)
    )

    layout["metrics"].update(Panel(create_metrics_table(stats), border_style="cyan"))
    layout["alerts"].update(create_alerts_panel(stats))
    layout["processes"].update(create_process_panel(procs))
    layout["summary"].update(create_summary_panel())

    return layout


def main():
    try:
        with Live(auto_refresh=False, screen=True) as live:
            while True:
                stats = get_stats()
                procs = get_process_snapshot()

                save(stats.cpu, stats.ram)

                layout = make_layout(stats, procs)
                live.update(layout, refresh=True)

                time.sleep(1)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()