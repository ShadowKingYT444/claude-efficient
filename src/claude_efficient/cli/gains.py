import click
from rich.console import Console
from rich.table import Table
from claude_efficient.analysis.telemetry import load

@click.command("gains")
def gains() -> None:
    """Show token savings dashboard."""
    console = Console()
    
    # Load from the global telemetry file
    records = load()
    
    console.print("[bold green]CE Token Savings (Global Scope)[/bold green]")
    console.print("=" * 60)
    console.print()
    
    if not records:
        console.print("No telemetry data found.")
        console.print("Run [bold cyan]ce run[/bold cyan] to start tracking savings.")
        return

    total_commands = len(records)
    
    total_input = sum((r.actual_input_tokens or 0) for r in records)
    total_output = sum((r.actual_output_tokens or 0) for r in records)
    total_cache_read = sum((r.actual_cache_read_tokens or 0) for r in records)
    
    # We estimate 1 token ≈ 4 characters
    total_chars_saved = sum((r.chars_saved or 0) for r in records)
    prompt_tokens_saved = total_chars_saved // 4
    
    # The user specifies: "cached tokens are basically worthless because 95% are saved"
    # This means a cache_read_token equates to 0.95 tokens saved.
    cache_tokens_saved = int(total_cache_read * 0.95)
    
    tokens_saved = prompt_tokens_saved + cache_tokens_saved
    
    # A total equivalent baseline: 
    # What we actually paid for: total_input + (total_cache_read * 0.05)
    # What we would have paid without CE: total_input + total_cache_read + prompt_tokens_saved
    total_baseline = total_input + total_cache_read + prompt_tokens_saved
    
    if total_baseline > 0:
        efficiency_pct = (tokens_saved / total_baseline) * 100.0
    else:
        efficiency_pct = 0.0
        
    total_time = sum((r.session_duration_s or 0.0) for r in records)
    avg_time = (total_time / total_commands) if total_commands > 0 else 0.0
    
    def fmt_num(n: int) -> str:
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n/1000:.1f}K"
        return str(n)
        
    def fmt_time(t: float) -> str:
        if t >= 60:
            m = int(t // 60)
            s = int(t % 60)
            return f"{m}m{s}s"
        elif t >= 1:
            return f"{t:.1f}s"
        else:
            return f"{int(t*1000)}ms"

    console.print(f"Total commands:   {total_commands}")
    console.print(f"Input tokens:     {fmt_num(total_input)}")
    console.print(f"Output tokens:    {fmt_num(total_output)}")
    console.print(f"Cached tokens:    {fmt_num(total_cache_read)}")
    console.print(f"Tokens saved:     {fmt_num(tokens_saved)} ({efficiency_pct:.1f}%)")
    console.print(f"Total exec time:  {fmt_time(total_time)} (avg {fmt_time(avg_time)})")
    
    filled = int(40 * (efficiency_pct / 100.0))
    filled = max(0, min(40, filled))
    empty = 40 - filled
    bar = f"[green]{'█' * filled}[/green][grey37]{'▒' * empty}[/grey37]"
    console.print(f"Efficiency meter: {bar} [bold yellow]{efficiency_pct:.1f}%[/bold yellow]")
    
    console.print()
    
    # We can show stats by model or mode if we want, replacing the static table.
    console.print("[bold green]By Model[/bold green]")
    table = Table(
        box=None,
        header_style="bold white",
        padding=(0, 2),
        show_edge=False,
        show_header=True,
    )
    table.add_column("Model", style="cyan")
    table.add_column("Runs", justify="right", style="white")
    table.add_column("Tokens Saved", justify="right", style="white")
    table.add_column("Avg%", justify="right")
    
    models = set(r.model for r in records)
    for model in models:
        m_records = [r for r in records if r.model == model]
        m_count = len(m_records)
        m_chars_saved = sum(r.chars_saved for r in m_records)
        m_cache = sum(r.actual_cache_read_tokens or 0 for r in m_records)
        m_input = sum(r.actual_input_tokens or 0 for r in m_records)
        
        m_saved = (m_chars_saved // 4) + int(m_cache * 0.95)
        m_baseline = m_input + m_cache + (m_chars_saved // 4)
        m_pct = (m_saved / m_baseline * 100.0) if m_baseline > 0 else 0.0
        
        table.add_row(
            model,
            str(m_count),
            fmt_num(m_saved),
            f"[green]{m_pct:.1f}%[/green]"
        )
        
    if models:
        console.print(table)
    console.print()
    console.print("─" * 60)
