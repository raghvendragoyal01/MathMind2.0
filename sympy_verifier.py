"""
sympy_verifier.py — MathMind 2.0 Verification Layer
====================================================
Takes LaTeX output from the OCR engine and:
  1. Parses it into SymPy expressions
  2. Attempts symbolic verification (LHS == RHS checks)
  3. Extracts solvable equations and computes solutions
  4. Reports confidence score per equation

This runs entirely on CPU — no GPU needed.
"""

import re
import sympy as sp
from dataclasses import dataclass, field
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Try importing latex2sympy2 — gracefully fall back if missing
try:
    from latex2sympy2 import latex2sympy, latex2latex
    HAS_LATEX2SYMPY = True
except ImportError:
    HAS_LATEX2SYMPY = False
    console.print(
        "[yellow]⚠ latex2sympy2 not installed. "
        "Run: pip install latex2sympy2[/yellow]"
    )


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ParsedEquation:
    raw_latex: str                         # The original LaTeX string
    sympy_expr: Optional[sp.Basic] = None  # Parsed SymPy expression
    lhs: Optional[sp.Basic] = None
    rhs: Optional[sp.Basic] = None
    is_equation: bool = False              # True if it contains '='
    solutions: dict = field(default_factory=dict)   # var → [solutions]
    verification: Optional[bool] = None    # True/False/None (None = couldn't verify)
    error: Optional[str] = None
    confidence: float = 0.0               # 0.0–1.0


@dataclass
class VerificationReport:
    raw_latex: str
    equations: list[ParsedEquation]
    total: int = 0
    parsed_ok: int = 0
    verified_ok: int = 0
    overall_confidence: float = 0.0


# ── LaTeX preprocessing ───────────────────────────────────────────────────────

def extract_equations_from_latex(latex_block: str) -> list[str]:
    """
    Extract individual equation strings from a LaTeX block.
    Handles: aligned environments, standalone equations, bare LaTeX.
    """
    # Strip aligned/equation environment wrappers
    cleaned = re.sub(
        r"\\begin\{(?:aligned|align\*?|equation\*?|cases)\}",
        "", latex_block
    )
    cleaned = re.sub(
        r"\\end\{(?:aligned|align\*?|equation\*?|cases)\}",
        "", cleaned
    )

    # Split on \\ (LaTeX line break in aligned environments)
    lines = re.split(r"\\\\", cleaned)

    # Split on & alignment markers, keep right-side
    equations = []
    for line in lines:
        parts = line.split("&")
        for part in parts:
            part = part.strip()
            if part and len(part) > 1:
                equations.append(part)

    # Remove empty / comment lines
    equations = [eq for eq in equations if eq and not eq.startswith("%")]
    return equations


def _clean_for_sympy(latex_str: str) -> str:
    """
    Light preprocessing to help latex2sympy2 parse better.
    Handles common OCR artifacts.
    """
    s = latex_str

    # Remove display math markers
    s = s.replace(r"\[", "").replace(r"\]", "")
    s = s.replace(r"\(", "").replace(r"\)", "")

    # Fix common OCR mistakes
    s = s.replace(r"\cdotp", r"\cdot")
    s = s.replace("×", r"\times")
    s = s.replace("÷", r"\div")

    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


# ── Core verification logic ───────────────────────────────────────────────────

def _parse_single(latex_str: str) -> ParsedEquation:
    """
    Parse one LaTeX equation string into a ParsedEquation.
    """
    eq = ParsedEquation(raw_latex=latex_str)

    if not HAS_LATEX2SYMPY:
        eq.error = "latex2sympy2 not available"
        return eq

    cleaned = _clean_for_sympy(latex_str)

    try:
        # Check if this is an equation (has = sign not part of ≤ ≥ ≠)
        has_eq = bool(re.search(r"(?<![<>!])=(?!=)", cleaned))
        eq.is_equation = has_eq

        if has_eq:
            # Split at the = sign to get LHS and RHS
            parts = re.split(r"(?<![<>!])=(?!=)", cleaned, maxsplit=1)
            if len(parts) == 2:
                lhs_str, rhs_str = parts
                try:
                    eq.lhs = latex2sympy(lhs_str.strip())
                    eq.rhs = latex2sympy(rhs_str.strip())
                    # Full expression as Eq()
                    eq.sympy_expr = sp.Eq(eq.lhs, eq.rhs)
                    eq.confidence = 0.7
                except Exception as e:
                    eq.error = f"Partial parse error: {e}"
                    eq.confidence = 0.3
        else:
            # Not an equation — just an expression
            eq.sympy_expr = latex2sympy(cleaned)
            eq.confidence = 0.6

    except Exception as e:
        eq.error = f"Parse failed: {type(e).__name__}: {e}"
        eq.confidence = 0.0

    return eq


def _verify_equation(eq: ParsedEquation) -> ParsedEquation:
    """
    Attempt symbolic verification: check if LHS - RHS simplifies to 0.
    Also attempts to solve for unknowns.
    """
    if not eq.is_equation or eq.lhs is None or eq.rhs is None:
        return eq

    try:
        diff = sp.simplify(eq.lhs - eq.rhs)

        if diff == 0:
            # LHS == RHS is an identity (always true)
            eq.verification = True
            eq.confidence = 1.0
        else:
            # LHS != RHS — it's a conditional equation → try to solve
            eq.verification = None  # Not true/false in general

            # Find free symbols (variables)
            free_vars = (eq.lhs - eq.rhs).free_symbols
            if free_vars:
                for var in free_vars:
                    try:
                        sols = sp.solve(sp.Eq(eq.lhs, eq.rhs), var)
                        if sols:
                            eq.solutions[str(var)] = [str(s) for s in sols]
                            eq.confidence = min(eq.confidence + 0.2, 1.0)
                    except (sp.SolveFailed, NotImplementedError):
                        pass  # Some equations are unsolvable symbolically

    except Exception as e:
        eq.error = (eq.error or "") + f" | Verification error: {e}"

    return eq


# ── Public API ────────────────────────────────────────────────────────────────

def verify_latex(latex_block: str, verbose: bool = True) -> VerificationReport:
    """
    Main entry point. Takes full LaTeX block from OCR engine → returns report.

    Args:
        latex_block: Raw LaTeX string from MathOCREngine.transcribe()
        verbose:     Print a rich table to terminal.

    Returns:
        VerificationReport with all parsed equations and their solutions.
    """
    equations_raw = extract_equations_from_latex(latex_block)

    parsed = []
    for raw in equations_raw:
        eq = _parse_single(raw)
        if eq.sympy_expr is not None:
            eq = _verify_equation(eq)
        parsed.append(eq)

    report = VerificationReport(
        raw_latex=latex_block,
        equations=parsed,
        total=len(parsed),
        parsed_ok=sum(1 for e in parsed if e.sympy_expr is not None),
        verified_ok=sum(1 for e in parsed if e.verification is True),
    )

    if parsed:
        report.overall_confidence = sum(e.confidence for e in parsed) / len(parsed)

    if verbose:
        _print_report(report)

    return report


def verify_expression_pair(lhs_latex: str, rhs_latex: str) -> dict:
    """
    Directly verify a single LHS = RHS pair given as separate LaTeX strings.
    Useful for testing specific equations.

    Returns:
        dict with 'equal' (bool), 'solutions', 'simplified_diff'
    """
    if not HAS_LATEX2SYMPY:
        return {"error": "latex2sympy2 not available"}

    try:
        lhs = latex2sympy(lhs_latex)
        rhs = latex2sympy(rhs_latex)
        diff = sp.simplify(lhs - rhs)

        result = {
            "lhs_sympy": str(lhs),
            "rhs_sympy": str(rhs),
            "equal": diff == 0,
            "simplified_diff": str(diff),
            "solutions": {},
        }

        if diff != 0:
            free_vars = diff.free_symbols
            for var in free_vars:
                sols = sp.solve(sp.Eq(lhs, rhs), var)
                result["solutions"][str(var)] = [str(s) for s in sols]

        return result

    except Exception as e:
        return {"error": str(e)}


# ── Terminal display ──────────────────────────────────────────────────────────

def _print_report(report: VerificationReport):
    """Print a rich formatted verification report."""
    console.print()

    # Summary panel
    confidence_color = (
        "green" if report.overall_confidence > 0.7
        else "yellow" if report.overall_confidence > 0.4
        else "red"
    )
    console.print(Panel(
        f"[bold]Equations found:[/bold] {report.total}  |  "
        f"[bold]Parsed OK:[/bold] {report.parsed_ok}  |  "
        f"[bold]Verified:[/bold] {report.verified_ok}  |  "
        f"[bold]Confidence:[/bold] [{confidence_color}]{report.overall_confidence:.0%}[/{confidence_color}]",
        title="[bold cyan]SymPy Verification Report[/bold cyan]",
    ))

    if not report.equations:
        console.print("[yellow]No equations extracted.[/yellow]")
        return

    # Per-equation table
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Raw LaTeX", style="cyan", ratio=3)
    table.add_column("SymPy Form", ratio=2)
    table.add_column("Solutions", ratio=2)
    table.add_column("Status", width=12)
    table.add_column("Conf", width=6)

    for i, eq in enumerate(report.equations, 1):
        sympy_str = str(eq.sympy_expr) if eq.sympy_expr is not None else f"[red]{eq.error or 'Failed'}[/red]"

        solutions_str = ""
        if eq.solutions:
            solutions_str = "\n".join(
                f"{var} = {', '.join(vals)}"
                for var, vals in eq.solutions.items()
            )
        elif eq.verification is True:
            solutions_str = "[green]Identity ✓[/green]"

        if eq.verification is True:
            status = "[green]✓ Identity[/green]"
        elif eq.solutions:
            status = "[blue]Solved[/blue]"
        elif eq.error:
            status = "[red]✗ Error[/red]"
        elif eq.sympy_expr:
            status = "[yellow]Parsed[/yellow]"
        else:
            status = "[red]Failed[/red]"

        conf_color = "green" if eq.confidence > 0.7 else "yellow" if eq.confidence > 0.4 else "red"

        table.add_row(
            str(i),
            eq.raw_latex[:60] + ("…" if len(eq.raw_latex) > 60 else ""),
            sympy_str[:50] + ("…" if len(sympy_str) > 50 else ""),
            solutions_str,
            status,
            f"[{conf_color}]{eq.confidence:.0%}[/{conf_color}]",
        )

    console.print(table)
    console.print()


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test with some sample LaTeX
    test_latex = r"""
    \begin{aligned}
    2x^2 + 3x - 5 = 0 \\
    \frac{d}{dx}(x^3) = 3x^2 \\
    \sin^2(\theta) + \cos^2(\theta) = 1 \\
    \int_0^1 x^2 \, dx = \frac{1}{3}
    \end{aligned}
    """

    console.print("[bold]Running SymPy Verifier test...[/bold]")
    report = verify_latex(test_latex, verbose=True)

    console.print("\n[bold]Direct pair verification test:[/bold]")
    result = verify_expression_pair(r"\sin^2(\theta) + \cos^2(\theta)", "1")
    console.print(result)
