import time
import sys
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout

from monitor import get_stats
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
    else:
        return 'green'


def get_status_text(value: float, metric: str) -> str:
    thresholds = THRESHOLDS.get(metric, {'warning': 70, 'critical': 85})

    if value >= thresholds['critical']:
        return '🔴 CRITICAL'
    elif value >= thresholds['warning']:
        return '🟡 WARNING'
    else:
        return '🟢 NORMAL'


def create_metrics_table(stats) -> Table:
    """Create metrics table with current stats"""
    table = Table(title="📊 Guardian System Monitor", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Value", style="magenta", width=20)
    table.add_column("Status", style="green", width=15)

    cpu_color = get_color(stats.cpu, 'cpu')
    cpu_status = get_status_text(stats.cpu, 'cpu')
    table.add_row("CPU Usage", f"[{cpu_color}]{stats.cpu:.1f}%[/{cpu_color}]", cpu_status)

    ram_color = get_color(stats.ram, 'ram')
    ram_status = get_status_text(stats.ram, 'ram')
    table.add_row("RAM Usage", f"[{ram_color}]{stats.ram:.1f}%[/{ram_color}]", ram_status)
    table.add_row("RAM Used", f"{stats.ram_mb:.0f} MB / {stats.ram_total_mb:.0f} MB", "")
    table.add_row("RAM Available", f"{stats.get_ram_available_mb():.0f} MB", "")

    disk_color = get_color(stats.disk, 'disk')
    disk_status = get_status_text(stats.disk, 'disk')
    table.add_row("Disk Usage", f"[{disk_color}]{stats.disk:.1f}%[/{disk_color}]", disk_status)
    table.add_row("Disk Free", f"{stats.disk_free_gb:.1f} GB / {stats.disk_total_gb:.1f} GB", "")

    table.add_row("Running Processes", str(stats.processes), "")

    return table


def create_alerts_panel(stats) -> Panel:
    """Create alerts panel with current alerts"""
    alerts = []

    if stats.cpu >= THRESHOLDS['cpu']['critical']:
        alerts.append("🔴 CPU CRITICAL - System under heavy load")
    elif stats.cpu >= THRESHOLDS['cpu']['warning']:
        alerts.append("🟡 CPU WARNING - Performance may degrade")

    if stats.ram >= THRESHOLDS['ram']['critical']:
        alerts.append("🔴 RAM CRITICAL - Memory running low")
    elif stats.ram >= THRESHOLDS['ram']['warning']:
        alerts.append("🟡 RAM WARNING - Close unnecessary apps")

    if stats.disk >= THRESHOLDS['disk']['critical']:
        alerts.append("🔴 DISK CRITICAL - Storage almost full")
    elif stats.disk >= THRESHOLDS['disk']['warning']:
        alerts.append("🟡 DISK WARNING - Clean up storage")

    if not alerts:
        alert_text = "✅ System Status: All systems normal"
        return Panel(alert_text, title="Status", border_style="green")
    else:
        alert_text = "\n".join(alerts)
        border_style = "red" if any("CRITICAL" in a for a in alerts) else "yellow"
        return Panel(alert_text, title="⚠️  Alerts", border_style=border_style)


def create_summary_panel() -> Panel:
    """Create summary panel with statistics"""
    summary = get_stats_summary()

    avg_cpu = summary.get('avg_cpu', 0.0) if summary.get('avg_cpu') is not None else 0.0
    avg_ram = summary.get('avg_ram', 0.0) if summary.get('avg_ram') is not None else 0.0
    max_cpu = summary.get('max_cpu', 0.0) if summary.get('max_cpu') is not None else 0.0
    max_ram = summary.get('max_ram', 0.0) if summary.get('max_ram') is not None else 0.0
    samples = summary.get('samples', 0) if summary.get('samples') is not None else 0

    summary_text = f"""
Last Hour Statistics:
├─ Samples: {samples}
├─ Avg CPU: {avg_cpu:.1f}%
├─ Avg RAM: {avg_ram:.1f}%
├─ Max CPU: {max_cpu:.1f}%
└─ Max RAM: {max_ram:.1f}%
    """

    return Panel(summary_text, title="📈 Stats", border_style="blue")


def make_layout(stats) -> Layout:
    layout = Layout()

    # Split into sections using ratios
    layout.split_column(
        Layout(name="metrics", ratio=3), # Takes up 3 parts of space
        Layout(name="alerts", ratio=1),  # Takes up 1 part
        Layout(name="summary", ratio=1)  # Takes up 1 part
    )

    # Update the content
    layout["metrics"].update(Panel(create_metrics_table(stats), border_style="cyan"))
    layout["alerts"].update(create_alerts_panel(stats))
    layout["summary"].update(create_summary_panel())

    return layout


def main():
    # 1. Do all your setup BEFORE the Live context
    init_db()

    # 2. Use the 'screen=True' argument in Live to create a dedicated
    # fullscreen view (like 'top' or 'htop'). This prevents scrolling.
    try:
        with Live(auto_refresh=False, screen=True) as live:
            while True:
                try:
                    stats = get_stats()
                    save(stats.cpu, stats.ram)  # Ensure no prints inside save()!

                    # Update the existing layout object
                    layout = make_layout(stats)
                    live.update(layout, refresh=True)

                    time.sleep(1)

                except Exception as e:
                    # In a Live display, standard prints mess up the UI.
                    # Use a log or temporary status instead.
                    time.sleep(1)

    except KeyboardInterrupt:
        pass  # Clean exit handled below

if __name__ == "__main__":
    main()