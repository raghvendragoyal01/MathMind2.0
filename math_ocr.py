"""
math_ocr.py — MathMind 2.0 · Main CLI
======================================
Combines the Perception Layer (Qwen2.5-VL-2B OCR)
with the Verification Layer (SymPy) into one command.

Usage examples:
  python math_ocr.py image.png
  python math_ocr.py image.png --type handwritten
  python math_ocr.py problem.pdf --page 0
  python math_ocr.py image.png --no-verify --save output.tex
  python math_ocr.py --batch folder/

Full options:
  --type    handwritten | printed | screenshot | diagram | auto (default: auto)
  --page    PDF page number, 0-indexed (default: 0)
  --verify  Run SymPy verification after OCR (default: True)
  --save    Save LaTeX output to a .tex file
  --batch   Process all images in a folder
"""

import sys
import time
import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from sympy_verifier import verify_latex

console = Console()

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
SUPPORTED_PDF = {".pdf"}

#for importing images (By Raghu)
#"C:\Users\Raghvendra Goyal\OneDrive\Creative Cloud Files\Desktop\MathMind\OCR\matheq.jpg" C:\MM\ 

# ── CLI definition ────────────────────────────────────────────────────────────

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "--type", "input_type",
    type=click.Choice(["handwritten", "printed", "screenshot", "diagram", "auto"]),
    default="auto",
    show_default=True,
    help="Type of mathematical content in the image.",
)
@click.option(
    "--page", "pdf_page",
    default=0,
    show_default=True,
    help="Page number to extract from PDF (0-indexed).",
)
@click.option(
    "--verify/--no-verify",
    default=True,
    show_default=True,
    help="Run SymPy verification on OCR output.",
)
@click.option(
    "--save",
    default=None,
    type=click.Path(),
    help="Save LaTeX output to this .tex file path.",
)
@click.option(
    "--batch",
    is_flag=True,
    default=False,
    help="Process all images in the given directory.",
)
@click.option(
    "--quiet", "-q",
    is_flag=True,
    default=False,
    help="Suppress verbose model loading output.",
)
def main(input_path, input_type, pdf_page, verify, save, batch, quiet):
    """
    \b
    MathMind 2.0 — Math OCR + SymPy Verification
    ─────────────────────────────────────────────
    Transcribes math problems from images/PDFs into LaTeX,
    then verifies and solves equations using SymPy.

    INPUT_PATH: path to image, PDF, or folder (with --batch).
    """
    console.print(Panel(
        "[bold]MathMind 2.0[/bold] · Math OCR Pipeline\n"
        "[dim]Qwen2.5-VL-2B (4-bit) + SymPy Verifier[/dim]",
        border_style="cyan",
    ))

    # Lazy import — only load model when actually needed
    from ocr_engine import MathOCREngine
    from sympy_verifier import verify_latex

    engine = MathOCREngine(verbose=not quiet)
    engine.load()

    input_path = Path(input_path)

    if batch:
        _run_batch(input_path, engine, input_type, verify, save)
    else:
        _run_single(input_path, engine, input_type, pdf_page, verify, save)


# ── Processing functions ──────────────────────────────────────────────────────

def _run_single(path: Path, engine, input_type: str, pdf_page: int, verify: bool, save):
    """Process one file."""
    suffix = path.suffix.lower()

    console.print(f"\n[bold]Processing:[/bold] [cyan]{path.name}[/cyan]")
    t0 = time.perf_counter()

    # ── OCR ──
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Transcribing image to LaTeX…", total=None)

        if suffix in SUPPORTED_PDF:
            result = engine.transcribe_pdf_page(path, page_number=pdf_page)
        elif suffix in SUPPORTED_IMAGES:
            result = engine.transcribe(path, input_type=input_type)
        else:
            console.print(f"[red]Unsupported format: {suffix}[/red]")
            console.print(f"Supported: {SUPPORTED_IMAGES | SUPPORTED_PDF}")
            sys.exit(1)

        progress.update(task, completed=True)

    elapsed_ocr = time.perf_counter() - t0

    # ── Display LaTeX output ──
    latex = result["latex"]
    console.print(Panel(
        latex,
        title=f"[bold green]LaTeX Output[/bold green] "
              f"· {result['tokens_generated']} tokens "
              f"· {elapsed_ocr:.1f}s",
        border_style="green",
    ))

    # ── Save to file ──
    if save:
        _save_latex(latex, save, path)

    # ── SymPy Verification ──
    if verify:
        console.print("\n[bold]Running SymPy verification…[/bold]")
        t1 = time.perf_counter()
        report = verify_latex(latex, verbose=True)
        elapsed_verify = time.perf_counter() - t1
        console.print(f"[dim]Verification completed in {elapsed_verify:.2f}s[/dim]\n")

        # Print solutions summary if any found
        solutions_found = any(eq.solutions for eq in report.equations)
        if solutions_found:
            console.print("[bold cyan]Solutions found:[/bold cyan]")
            for eq in report.equations:
                if eq.solutions:
                    for var, vals in eq.solutions.items():
                        console.print(f"  [green]{var}[/green] = {', '.join(vals)}")
            console.print()


def _run_batch(folder: Path, engine, input_type: str, verify: bool, save_dir):
    """Process all images in a folder."""
    if not folder.is_dir():
        console.print(f"[red]{folder} is not a directory.[/red]")
        sys.exit(1)

    files = [
        f for f in sorted(folder.iterdir())
        if f.suffix.lower() in SUPPORTED_IMAGES | SUPPORTED_PDF
    ]

    if not files:
        console.print(f"[yellow]No supported images found in {folder}[/yellow]")
        sys.exit(0)

    console.print(f"\n[bold]Batch mode:[/bold] {len(files)} files found\n")

    from sympy_verifier import verify_latex

    results = []
    for i, file in enumerate(files, 1):
        console.rule(f"[dim]File {i}/{len(files)}: {file.name}[/dim]")
        try:
            suffix = file.suffix.lower()
            if suffix in SUPPORTED_PDF:
                result = engine.transcribe_pdf_page(file)
            else:
                result = engine.transcribe(file, input_type=input_type)

            console.print(Panel(
                result["latex"][:500] + ("…" if len(result["latex"]) > 500 else ""),
                title=f"[green]{file.name}[/green]",
                border_style="green",
            ))

            if verify:
                report = verify_latex(result["latex"], verbose=False)
                status = (
                    f"[green]{report.parsed_ok}/{report.total} parsed · "
                    f"{report.overall_confidence:.0%} confidence[/green]"
                )
                console.print(f"  SymPy: {status}")

            save_path = None
            if save_dir:
                save_path = Path(save_dir) / (file.stem + ".tex")
            _save_latex(result["latex"], save_path, file)

            results.append({"file": file.name, "success": True, "latex": result["latex"]})

        except Exception as e:
            console.print(f"[red]Error processing {file.name}: {e}[/red]")
            results.append({"file": file.name, "success": False, "error": str(e)})

    # Final summary
    success = sum(1 for r in results if r["success"])
    console.print(Panel(
        f"[bold]Batch complete:[/bold] {success}/{len(results)} files processed successfully",
        border_style="cyan",
    ))


def _save_latex(latex: str, save_path, source_path: Path):
    """Save LaTeX to file with a minimal LaTeX document wrapper."""
    if save_path is None:
        return

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    content = (
        "% Auto-generated by MathMind 2.0 OCR Engine\n"
        f"% Source: {source_path.name}\n\n"
        "\\documentclass{article}\n"
        "\\usepackage{amsmath, amssymb}\n"
        "\\begin{document}\n\n"
        "\\[\n"
        f"{latex}\n"
        "\\]\n\n"
        "\\end{document}\n"
    )

    save_path.write_text(content, encoding="utf-8")
    console.print(f"[dim]LaTeX saved to: {save_path}[/dim]")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
