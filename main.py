import time
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from monitor import get_stats
from db import save

alert_message = ""

def make_layout(cpu, ram):
    global alert_message

    layout = Layout()

    table = Table(title="Guardian Monitor")
    table.add_column("Metric")
    table.add_column("Value")

    cpu_color = "red" if cpu > 80 else "green"
    ram_color = "red" if ram > 80 else "green"

    table.add_row("CPU", f"[{cpu_color}]{cpu}%[/{cpu_color}]")
    table.add_row("RAM", f"[{ram_color}]{ram}%[/{ram_color}]")

    if cpu > 80 or ram > 80:
        alert_message = "⚠ High usage detected!"
    else:
        alert_message = "System stable"

    layout.split(
        Layout(Panel(table), size=8),
        Layout(Panel(alert_message, title="Status"))
    )

    return layout

with Live(refresh_per_second=2) as live:
    while True:
        cpu, ram = get_stats()
        save(cpu, ram)

        live.update(make_layout(cpu, ram))
        time.sleep(1)