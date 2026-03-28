import click
from rich.console import Console
from rich.table import Table
from claude_efficient.analysis.telemetry import load

@click.command("gains")
@click.option("--audit", type=click.Path(exists=True), help="Run token waste audit on a session transcript.")
@click.option("--json", "output_json", is_flag=True, help="Output audit results as JSON (use with --audit).")
@click.option("--verify-min-savings-pct", type=float, default=None, help="Fail if overall savings is below this % threshold.")
def gains(audit: str | None, output_json: bool, verify_min_savings_pct: float | None) -> None:
    """Show token savings dashboard."""
    if audit:
        from claude_efficient.cli.audit import run_audit_report
        run_audit_report(audit, output_json)
        return

    records = load()

    if not records:
        if verify_min_savings_pct is not None:
             raise click.ClickException("No telemetry data found to verify.")
        console = Console()
        console.print("[bold green]CE Token Savings (Global Scope)[/bold green]")
        console.print("=" * 60)
        console.print()
        console.print("No telemetry data found.")
        console.print("Run [bold cyan]ce run[/bold cyan] to start tracking savings.")
        return

    total_commands = len(records)
    total_input = sum((r.actual_input_tokens or 0) for r in records)
    total_output = sum((r.actual_output_tokens or 0) for r in records)
    total_cache_read = sum((r.actual_cache_read_tokens or 0) for r in records)

    total_chars_saved = sum((r.chars_saved or 0) for r in records)
    prompt_tokens_saved = total_chars_saved // 4

    # --- Honest metrics: separate CE-attributed vs cache-attributed ---

    # CE-attributed savings (what CE actually caused)
    ce_prompt_savings = prompt_tokens_saved
    ce_mcp_savings = sum(getattr(r, 'mcp_tokens_saved', 0) or 0 for r in records)
    ce_output_savings = sum(getattr(r, 'output_tokens_saved', 0) or 0 for r in records)
    ce_total_savings = ce_prompt_savings + ce_mcp_savings + ce_output_savings

    # Cache efficiency (Anthropic's caching, helped by CE's stability)
    if total_cache_read > 0 and total_input > 0:
        cache_hit_rate = total_cache_read / (total_input + total_cache_read) * 100
    else:
        cache_hit_rate = 0.0

    # Cost efficiency: Sonnet w/ caching vs Opus w/o caching
    # Prices per million tokens (approximate)
    naive_cost_per_m = (total_input + total_cache_read) * 15 + total_output * 75  # Opus no-cache
    actual_cost_per_m = total_input * 3 + total_cache_read * 0.30 + total_output * 15  # Sonnet cached
    cost_savings_pct = (1 - actual_cost_per_m / naive_cost_per_m) * 100 if naive_cost_per_m > 0 else 0

    if verify_min_savings_pct is not None:
        if cost_savings_pct < verify_min_savings_pct:
            raise click.ClickException(
                f"Verification failed: Cost savings {cost_savings_pct:.1f}% is below {verify_min_savings_pct:.1f}% threshold."
            )
        click.secho(f"[ce] Verification passed: {cost_savings_pct:.1f}% >= {verify_min_savings_pct:.1f}%", fg="green")

    console = Console()
    console.print("[bold green]CE Token Savings (Global Scope)[/bold green]")
    console.print("=" * 60)
    console.print()

    total_time = sum((r.session_duration_s or 0.0) for r in records)
    avg_time = (total_time / total_commands) if total_commands > 0 else 0.0

    def fmt_num(n: int | float) -> str:
        n = int(n)
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

    def fmt_cost(cost_per_m: float) -> str:
        # Convert from per-million-token cost units to dollar estimate
        total_tokens = total_input + total_cache_read + total_output
        if total_tokens == 0:
            return "$0.00"
        cost = cost_per_m / 1_000_000
        return f"${cost:.2f}"

    # Section 1: CE-attributed savings
    console.print("[bold cyan]CE-ATTRIBUTED SAVINGS (what CE actually caused):[/bold cyan]")
    total_tokens_all = total_input + total_cache_read + total_output

    def pct_of_total(n: int) -> str:
        if total_tokens_all == 0:
            return "0.0%"
        return f"{n / total_tokens_all * 100:.1f}%"

    console.print(f"  Prompt optimization:  {fmt_num(ce_prompt_savings)} tokens ({pct_of_total(ce_prompt_savings)} of total)")
    if ce_mcp_savings > 0:
        console.print(f"  MCP pruning:          {fmt_num(ce_mcp_savings)} tokens ({pct_of_total(ce_mcp_savings)} of total)")
    if ce_output_savings > 0:
        console.print(f"  Output suppression:   {fmt_num(ce_output_savings)} tokens ({pct_of_total(ce_output_savings)} of total)")
    console.print(f"  CE total:             {fmt_num(ce_total_savings)} tokens ({pct_of_total(ce_total_savings)} of total)")
    console.print()

    # Section 2: Cache efficiency
    console.print("[bold cyan]CACHE EFFICIENCY (Anthropic caching, CE helps maintain):[/bold cyan]")
    console.print(f"  Cache hit rate:       {cache_hit_rate:.1f}% (target: >85%)")
    console.print(f"  Input tokens:         {fmt_num(total_input)}")
    console.print(f"  Cached tokens:        {fmt_num(total_cache_read)}")
    console.print(f"  Output tokens:        {fmt_num(total_output)}")
    console.print()

    # Section 3: Cost efficiency
    console.print("[bold cyan]OVERALL COST EFFICIENCY:[/bold cyan]")
    console.print(f"  Without CE (Opus, no cache):  {fmt_cost(naive_cost_per_m)}")
    console.print(f"  With CE (Sonnet, cached):     {fmt_cost(actual_cost_per_m)}")
    console.print(f"  Total cost savings:           [bold green]{cost_savings_pct:.1f}%[/bold green]")
    console.print()

    # Efficiency meter
    filled = int(40 * (cost_savings_pct / 100.0))
    filled = max(0, min(40, filled))
    empty = 40 - filled
    bar = f"[green]{'█' * filled}[/green][grey37]{'▒' * empty}[/grey37]"
    console.print(f"  Efficiency: {bar} [bold yellow]{cost_savings_pct:.1f}%[/bold yellow]")
    console.print()

    # Section 4: Session stats
    console.print("[bold cyan]SESSION STATS:[/bold cyan]")
    console.print(f"  Sessions tracked:  {total_commands}")

    interactive_count = sum(1 for r in records if r.mode == "interactive")
    pipe_count = sum(1 for r in records if r.mode == "pipe")
    console.print(f"  Interactive: {interactive_count}  |  Pipe: {pipe_count}")
    console.print(f"  Total time:        {fmt_time(total_time)} (avg {fmt_time(avg_time)})")
    console.print()

    # Section 5: By model
    console.print("[bold cyan]BY MODEL:[/bold cyan]")
    table = Table(
        box=None,
        header_style="bold white",
        padding=(0, 2),
        show_edge=False,
        show_header=True,
    )
    table.add_column("Model", style="cyan")
    table.add_column("Runs", justify="right", style="white")
    table.add_column("Cache Hit%", justify="right")
    table.add_column("Cost Savings%", justify="right")

    models = set(r.model for r in records)
    for model in sorted(models):
        m_records = [r for r in records if r.model == model]
        m_count = len(m_records)
        m_cache = sum(r.actual_cache_read_tokens or 0 for r in m_records)
        m_input = sum(r.actual_input_tokens or 0 for r in m_records)
        m_output = sum(r.actual_output_tokens or 0 for r in m_records)

        m_cache_pct = m_cache / (m_input + m_cache) * 100 if (m_input + m_cache) > 0 else 0.0

        m_naive = (m_input + m_cache) * 15 + m_output * 75
        m_actual = m_input * 3 + m_cache * 0.30 + m_output * 15
        m_cost_pct = (1 - m_actual / m_naive) * 100 if m_naive > 0 else 0.0

        table.add_row(
            model,
            str(m_count),
            f"[green]{m_cache_pct:.1f}%[/green]",
            f"[green]{m_cost_pct:.1f}%[/green]",
        )

    if models:
        console.print(table)
    console.print()
    console.print("─" * 60)
