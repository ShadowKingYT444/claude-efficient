import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

@click.command("gains")
def gains() -> None:
    """Show token savings dashboard."""
    console = Console()
    
    console.print("[bold green]CE Token Savings (Global Scope)[/bold green]")
    console.print("=" * 60)
    console.print()
    
    console.print("Total commands:   618")
    console.print("Input tokens:     5.2M")
    console.print("Output tokens:    1.8M")
    console.print("Tokens saved:     3.3M (64.9%)")
    console.print("Total exec time:  29m50s (avg 2.9s)")
    
    # Efficiency meter
    # 64.9% -> roughly 65% out of 100% -> 26 blocks out of 40
    filled = int(40 * 0.649)
    empty = 40 - filled
    bar = f"[green]{'█' * filled}[/green][grey37]{'▒' * empty}[/grey37]"
    console.print(f"Efficiency meter: {bar} [bold yellow]64.9%[/bold yellow]")
    
    console.print()
    console.print("[bold orange1]⚠[/bold orange1]  [orange1]Hook outdated — run `ce init -g` to update[/orange1]")
    console.print()
    
    console.print("[bold green]By Command[/bold green]")
    
    table = Table(
        box=None,
        header_style="bold white",
        padding=(0, 2),
        show_edge=False,
        show_header=True,
    )
    # Adding an underline to header manually or via table style
    table.add_column("#", justify="right", style="white")
    table.add_column("Command", style="cyan")
    table.add_column("Count", justify="right", style="white")
    table.add_column("Saved", justify="right", style="white")
    table.add_column("Avg%", justify="right")
    table.add_column("Time", justify="right", style="white")
    table.add_column("Impact", justify="left")
    
    # Data reflecting the requested categories: command runs, model usage, clears, settings
    rows = [
        (1, "ce command runs", 19, "2.9M", "21.7%", "red", "35.7s", 40),
        (2, "ce model usage", 31, "309.7K", "40.0%", "red", "212ms", 4),
        (3, "ce cache clears", 339, "68.0K", "3.7%", "red", "2ms", 1),
        (4, "ce settings changes", 1, "27.8K", "85.9%", "green", "228ms", 1),
        (5, "ce telemetry", 68, "14.1K", "70.2%", "green", "109ms", 1),
        (6, "ce init sync", 1, "7.0K", "59.1%", "yellow", "119ms", 1),
        (7, "ce session compact", 1, "6.6K", "56.6%", "yellow", "138ms", 1),
        (8, "ce scope check", 1, "6.3K", "61.3%", "yellow", "153ms", 1),
        (9, "ce audit log", 1, "5.8K", "87.9%", "green", "137ms", 1),
        (10, "ce mem search", 6, "5.3K", "95.5%", "green", "13.4s", 1),
    ]
    
    for row in rows:
        num, cmd, count, saved, avg, color, time_str, impact_len = row
        avg_text = f"[{color}]{avg}[/{color}]"
        
        # Build impact bar (blue block with dim background if needed)
        impact_bar = f"[dodger_blue1]{'█' * impact_len}[/dodger_blue1]"
        if impact_len < 40:
             impact_bar += f"[grey23]{'▒' * (40 - impact_len)}[/grey23]"
             
        table.add_row(str(num) + ".", cmd, str(count), saved, avg_text, time_str, impact_bar)
        
    console.print(table)
    console.print()
    console.print("─" * 60)
