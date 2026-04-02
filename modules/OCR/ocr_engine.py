"""
ocr_engine.py — MathMind 2.0 Perception Layer
=============================================
Runs Qwen2.5-VL-2B-Instruct in 4-bit quantization.
Fits comfortably in 4GB VRAM (RTX 3050).

Supports:
  - Handwritten math problems (image/photo)
  - Printed textbook pages (image or PDF)
  - Screenshots of equations
  - Geometric diagrams with labels

Output: Structured LaTeX preserving spatial semantics.
"""

import torch
import warnings
from pathlib import Path
from typing import Union

from PIL import Image
from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor,
    BitsAndBytesConfig,
)
from qwen_vl_utils import process_vision_info
from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner

console = Console()

# ── Model config ──────────────────────────────────────────────────────────────
MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"  # 3B fits in 4GB with 4-bit quant

# 4-bit quantization config — critical for 4GB VRAM
BNB_CONFIG = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",          # NormalFloat4 — best quality for 4-bit
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,     # Nested quantization saves ~0.4GB extra
)

# ── System prompt: instructs the VLM to output clean LaTeX ───────────────────
SYSTEM_PROMPT = """You are a precise mathematical OCR engine.
Your ONLY job is to transcribe the mathematical content from images into structured LaTeX.

Rules:
1. Preserve ALL spatial relationships: fractions stay as \\frac{}{}, superscripts as ^{}, subscripts as _{}.
2. For geometric diagrams: describe the diagram briefly in plain text, then transcribe any equations or labels in LaTeX.
3. For handwritten content: transcribe exactly what is written, even if it looks like an intermediate step.
4. Wrap the entire output in: \\begin{aligned} ... \\end{aligned}
5. If multiple equations exist, separate them with \\\\.
6. DO NOT solve or simplify. Just transcribe faithfully.
7. If something is unclear, mark it with \\text{[unclear]}.

Output ONLY the LaTeX block. No explanations, no markdown fences."""

# ── OCR prompts per input type ────────────────────────────────────────────────
PROMPTS = {
    "handwritten": (
        "This is a handwritten mathematics problem. "
        "Transcribe every symbol, digit, and operator exactly as written into LaTeX. "
        "Pay close attention to exponents, subscripts, and fractions."
    ),
    "printed": (
        "This is a printed mathematics textbook page or problem. "
        "Transcribe all mathematical content into LaTeX, preserving layout."
    ),
    "screenshot": (
        "This is a screenshot containing one or more mathematical equations. "
        "Extract and transcribe all equations into LaTeX."
    ),
    "diagram": (
        "This is a geometric diagram or mathematical figure. "
        "First describe the geometric elements (e.g., 'Circle with center O, tangent line at point P'). "
        "Then transcribe all labeled equations, angles, and measurements into LaTeX."
    ),
    "auto": (
        "Transcribe all mathematical content from this image into structured LaTeX, "
        "preserving all spatial relationships and notation."
    ),
}


class MathOCREngine:
    """
    Wrapper around Qwen2.5-VL-2B for math OCR.
    Loads once, runs many times — no re-loading between images.
    """

    """Initialization is lightweight. Call .load() to load the model into GPU memory.
    This separation allows for better control over when the heavy loading happens,
    especially in larger applications where you might want to load the model at a specific time."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.model = None
        self.processor = None
        self._loaded = False

    def load(self):
        """Load model into GPU memory. Call once before processing."""
        if self._loaded:
            return

        if self.verbose:
            console.print(Panel(
                f"[bold cyan]Loading {MODEL_ID}[/bold cyan]\n"
                "[dim]4-bit quantized · ~1.5 GB VRAM · one-time load[/dim]",
                title="[bold]MathMind 2.0 — Perception Layer[/bold]",
            ))

        warnings.filterwarnings("ignore", category=UserWarning)

        # Load model with 4-bit quant — device_map="auto" handles split across CPU/GPU
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            MODEL_ID,
            quantization_config=BNB_CONFIG,
            device_map="auto",          # Auto-places layers on GPU/CPU as VRAM allows
            torch_dtype=torch.float16,
            trust_remote_code=True,
        )
        self.model.eval()

        # min/max pixels: keeps small images from over-tokenizing,
        # and large images from OOM-ing on 4GB GPU
        self.processor = AutoProcessor.from_pretrained(
            MODEL_ID,
            min_pixels=256 * 28 * 28,   # ~200K pixels min
            max_pixels=512 * 28 * 28,   # ~400K pixels max — safe for 4GB
            trust_remote_code=True,
        )

        self._loaded = True
        if self.verbose:
            console.print("[green]✓ Model loaded successfully[/green]\n")

    def _prepare_messages(self, image: Image.Image, input_type: str) -> list:
        """Build the chat message structure Qwen2.5-VL expects."""
        user_prompt = PROMPTS.get(input_type, PROMPTS["auto"])

        return [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image,           # PIL Image — qwen_vl_utils handles encoding
                    },
                    {
                        "type": "text",
                        "text": user_prompt,
                    },
                ],
            },
        ]

    @torch.inference_mode()
    def transcribe(
        self,
        image: Union[Image.Image, str, Path],
        input_type: str = "auto",
        max_new_tokens: int = 1024,
    ) -> dict:
        """
        Transcribe a single image to LaTeX.

        Args:
            image:          PIL Image OR path to image file.
            input_type:     One of: 'handwritten', 'printed', 'screenshot', 'diagram', 'auto'.
            max_new_tokens: Max LaTeX tokens to generate (1024 handles most problems).

        Returns:
            dict with keys:
              - 'latex': the raw LaTeX string
              - 'input_type': what was used
              - 'tokens_generated': how many tokens were output
        """
        assert self._loaded, "Call .load() before .transcribe()"

        # Accept file paths
        if not isinstance(image, Image.Image):
            image = Image.open(image).convert("RGB")

        # Resize if the image is very large — prevents VRAM spikes
        image = _safe_resize(image, max_side=1024)

        messages = self._prepare_messages(image, input_type)

        # Apply Qwen chat template
        text_input = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        # Process vision info (encodes image into visual tokens)
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = self.processor(
            text=[text_input],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        # Generate — greedy decoding is deterministic and fast for OCR
        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,            # Greedy — OCR should be deterministic
            temperature=None,
            top_p=None,
            repetition_penalty=1.05,   # Slight penalty to avoid looping on unclear content
            pad_token_id=self.processor.tokenizer.eos_token_id,
        )

        # Decode only the newly generated tokens (strip the prompt)
        generated_ids = [
            out[len(inp):]
            for inp, out in zip(inputs.input_ids, output_ids)
        ]
        latex_output = self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()

        return {
            "latex": latex_output,
            "input_type": input_type,
            "tokens_generated": len(generated_ids[0]),
        }

    def transcribe_pdf_page(
        self,
        pdf_path: Union[str, Path],
        page_number: int = 0,
        dpi: int = 150,
    ) -> dict:
        """
        Convert a PDF page to image and transcribe it.

        Args:
            pdf_path:    Path to PDF file.
            page_number: 0-indexed page number.
            dpi:         Render DPI — 150 is good quality and stays within pixel budget.

        Returns:
            Same dict as transcribe().
        """
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        if page_number >= len(doc):
            raise ValueError(f"PDF has {len(doc)} pages, requested page {page_number}")

        page = doc[page_number]
        mat = fitz.Matrix(dpi / 72, dpi / 72)   # 72 DPI is PDF default
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()

        return self.transcribe(img, input_type="printed")


# ── Helper ────────────────────────────────────────────────────────────────────

def _safe_resize(image: Image.Image, max_side: int = 1024) -> Image.Image:
    """
    Resize image so neither side exceeds max_side.
    Preserves aspect ratio. Skips if already small enough.
    """
    w, h = image.size
    if max(w, h) <= max_side:
        return image
    scale = max_side / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    return image.resize((new_w, new_h), Image.LANCZOS)


# ── Quick standalone test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        console.print("[red]Usage: python ocr_engine.py <image_path> [input_type][/red]")
        console.print("input_type: handwritten | printed | screenshot | diagram | auto")
        sys.exit(1)

    img_path = sys.argv[1]
    itype = sys.argv[2] if len(sys.argv) > 2 else "auto"

    engine = MathOCREngine(verbose=True)
    engine.load()

    result = engine.transcribe(img_path, input_type=itype)

    console.print(Panel(
        result["latex"],
        title=f"[bold green]LaTeX Output[/bold green] · {result['tokens_generated']} tokens",
        border_style="green",
    ))
