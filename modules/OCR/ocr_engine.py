"""
ocr_engine.py — MathMind 2.0 Perception Layer
=============================================
Runs Qwen2.5-VL-2B-Instruct.
Dynamically adapts to hardware (NVIDIA CUDA, Apple MPS, or CPU).

Supports:
  - Handwritten math problems (image/photo)
  - Printed textbook pages (image or PDF)
  - Screenshots of equations
  - Geometric diagrams with labels
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

console = Console()

# ── Model config ──────────────────────────────────────────────────────────────
MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"

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
    "handwritten": "This is a handwritten mathematics problem. Transcribe exactly as written into LaTeX.",
    "printed": "This is a printed mathematics textbook page or problem. Transcribe all mathematical content into LaTeX.",
    "screenshot": "This is a screenshot containing mathematical equations. Extract and transcribe all equations into LaTeX.",
    "diagram": "This is a geometric diagram. Describe the geometry, then transcribe equations and labels into LaTeX.",
    "auto": "Transcribe all mathematical content from this image into structured LaTeX, preserving spatial relationships."
}


class MathOCREngine:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.model = None
        self.processor = None
        self._loaded = False

    def load(self):
        """Load model dynamically based on available hardware."""
        if self._loaded:
            return

        # --- Hardware Detection Logic ---
        use_quantization = False
        device_map = "auto"
        torch_dtype = torch.float16

        if torch.cuda.is_available():
            hardware_msg = "[bold green]Backend: NVIDIA CUDA detected[/bold green] · Using 4-bit NF4 Quantization (RTX 3050 safe)"
            use_quantization = True
        elif torch.backends.mps.is_available():
            hardware_msg = "[bold blue]Backend: Apple Silicon (MPS) detected[/bold blue] · Running standard FP16 (Uses ~6GB Unified Memory)"
            device_map = "mps" # Force MPS for Mac
        else:
            hardware_msg = "[bold yellow]Backend: CPU only detected[/bold yellow] · Inference will be slow"
            device_map = "cpu"
            torch_dtype = torch.float32

        if self.verbose:
            console.print(Panel(
                f"[bold cyan]Loading {MODEL_ID}[/bold cyan]\n{hardware_msg}",
                title="[bold]MathMind 2.0 — Perception Layer[/bold]",
            ))

        warnings.filterwarnings("ignore", category=UserWarning)

        # Build kwargs dynamically
        model_kwargs = {
            "device_map": device_map,
            "torch_dtype": torch_dtype,
            "trust_remote_code": True,
        }

        # Only apply bitsandbytes if we are on an NVIDIA GPU
        if use_quantization:
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )

        # Load Model
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            MODEL_ID,
            **model_kwargs
        )
        self.model.eval()

        self.processor = AutoProcessor.from_pretrained(
            MODEL_ID,
            min_pixels=256 * 28 * 28,
            max_pixels=512 * 28 * 28,
            trust_remote_code=True,
        )

        self._loaded = True
        if self.verbose:
            console.print("[green]✓ Model loaded successfully[/green]\n")

    def _prepare_messages(self, image: Image.Image, input_type: str) -> list:
        user_prompt = PROMPTS.get(input_type, PROMPTS["auto"])
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

    @torch.inference_mode()
    def transcribe(self, image: Union[Image.Image, str, Path], input_type: str = "auto", max_new_tokens: int = 1024) -> dict:
        assert self._loaded, "Call .load() before .transcribe()"

        if not isinstance(image, Image.Image):
            image = Image.open(image).convert("RGB")

        image = _safe_resize(image, max_side=1024)
        messages = self._prepare_messages(image, input_type)

        text_input = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = self.processor(
            text=[text_input],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            repetition_penalty=1.05,
            pad_token_id=self.processor.tokenizer.eos_token_id,
        )

        generated_ids = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
        latex_output = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

        return {
            "latex": latex_output,
            "input_type": input_type,
            "tokens_generated": len(generated_ids[0]),
        }

    def transcribe_pdf_page(self, pdf_path: Union[str, Path], page_number: int = 0, dpi: int = 150) -> dict:
        import fitz
        doc = fitz.open(str(pdf_path))
        page = doc[page_number]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()
        return self.transcribe(img, input_type="printed")

def _safe_resize(image: Image.Image, max_side: int = 1024) -> Image.Image:
    w, h = image.size
    if max(w, h) <= max_side:
        return image
    scale = max_side / max(w, h)
    return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)