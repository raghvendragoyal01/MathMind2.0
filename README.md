# MathMind 2.0 🧠
### A Neuro-Symbolic Architecture for Advanced Mathematical Reasoning

**Author:** Raghvendra Goyal  
**Started:** January 2026  
**Status:** 🟡 In Progress — MVP (Perception Layer + Verification Layer complete)

---

## What is MathMind 2.0?

MathMind 2.0 is an open-source, end-to-end AI system that:
- 📸 **Reads** math problems from images, PDFs, handwritten photos
- 🧠 **Reasons** through them using System 2 thinking (DeepSeek-R1)
- ✅ **Verifies** every step symbolically using SymPy
- 💻 **Runs** on consumer-grade hardware (RTX 3050 4GB+)

> MathMind 2.0 = **Eyes** (Qwen VLM) + **Brain** (DeepSeek R1) + **Calculator** (SymPy) + **Teacher** (PRM)

---

## Architecture Overview

```
📸 User Input (Image / PDF / Handwritten Photo)
        ↓
🔵 PERCEPTION LAYER        → Qwen2.5-VL-3B (OCR-free LaTeX extraction)
        ↓
🟣 COGNITIVE LAYER         → DeepSeek-R1-Distill (Chain-of-Thought reasoning)  [🔄 Coming]
        ↓
🟢 EXECUTION LAYER         → Python Sandbox + SymPy (Tool-Integrated Reasoning) [🔄 Coming]
        ↓
🔴 VERIFICATION LAYER      → Process Reward Model (Step-level verification)      [🔄 Coming]
        ↓
✅ Final Output (LaTeX + Solutions + Confidence Score)
```

---

## Current Progress

| Module | Status | Description |
|--------|--------|-------------|
| Perception Layer (OCR) | ✅ Complete | Qwen2.5-VL-3B, 4-bit quantized |
| SymPy Verifier | ✅ Complete | Equation parsing + solving |
| CLI Pipeline | ✅ Complete | Single image, PDF, batch |
| Cognitive Layer | 🔄 In Progress | DeepSeek-R1-Distill integration |
| GRPO Training | 🔄 Planned | Reinforcement Learning loop |
| Process Reward Model | 🔄 Planned | Step-level verification |
| Streamlit UI | 🔄 Planned | Web interface |

---

## Folder Structure

```
MathMind2/
├── ocr_engine.py          ← Perception Layer (Qwen2.5-VL-3B)
├── sympy_verifier.py      ← Verification Layer (SymPy)
├── math_ocr.py            ← Main CLI entry point
├── requirements.txt       ← All dependencies
└── README.md              ← This file
```

> 📌 More folders will be added as modules are built:
> `cognitive/`, `training/`, `sandbox/`, `ui/`, `api/`

---

## Setup & Installation

### Requirements
- Python 3.11+
- NVIDIA GPU with CUDA (minimum 4GB VRAM)
- CUDA 12.1+

### Step 1 — Install PyTorch (CUDA)
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### Step 2 — Install dependencies
```bash
pip install -r requirements.txt
```

> ⚠️ First run will download ~6GB model weights (Qwen2.5-VL-3B).  
> Cached at `~/.cache/huggingface/` — only happens once.

### Step 3 — Verify GPU
```bash
python -c "import torch; print('GPU:', torch.cuda.get_device_name(0))"
```

---

## Usage

### Basic usage
```bash
python math_ocr.py image.jpg
```

### Specify input type (better accuracy)
```bash
python math_ocr.py homework.jpg --type handwritten
python math_ocr.py textbook.png --type printed
python math_ocr.py equation.png --type screenshot
python math_ocr.py geometry.jpg --type diagram
```

### PDF support
```bash
python math_ocr.py textbook.pdf --page 0
```

### Save LaTeX output
```bash
python math_ocr.py image.jpg --save output.tex
```

### Batch process a folder
```bash
python math_ocr.py ./problems/ --batch
```

### Skip SymPy verification
```bash
python math_ocr.py image.jpg --no-verify
```

---

## Use as Python Library

```python
from ocr_engine import MathOCREngine
from sympy_verifier import verify_latex

# Load model once
engine = MathOCREngine()
engine.load()

# Transcribe image to LaTeX
result = engine.transcribe("problem.jpg", input_type="printed")
print(result["latex"])

# Verify and solve
report = verify_latex(result["latex"])
for eq in report.equations:
    if eq.solutions:
        print(f"Solutions: {eq.solutions}")
```

---

## Sample Output

```
╭─ LaTeX Output ─────────────────────────────╮
│ \begin{aligned}                             │
│ \int \frac{x^3 - 1}{x^2} dx \\             │
│ \int (x^{\frac{2}{3}} + 1) dx              │
│ \end{aligned}                               │
╰─────────────────────────────────────────────╯

╭─ SymPy Verification Report ─────────────────╮
│ Equations: 3 | Parsed: 3 | Confidence: 98% │
│ x = 1, x = -5/2                            │
╰─────────────────────────────────────────────╯
```

---

## VRAM Usage (RTX 3050 4GB)

| Component | VRAM |
|-----------|------|
| Qwen2.5-VL-3B (4-bit) | ~1.8 GB |
| Visual tokens | ~0.2 GB |
| KV Cache (MLA) | ~0.1 GB |
| PyTorch overhead | ~0.4 GB |
| **Total** | **~2.5 GB** |
| **Headroom** | **~1.5 GB** |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| OCR / Perception | Qwen2.5-VL-3B-Instruct |
| Quantization | BitsAndBytes (4-bit NF4) |
| Math Verification | SymPy + latex2sympy2 |
| PDF Processing | PyMuPDF (fitz) |
| CLI | Click |
| Terminal UI | Rich |
| Inference (upcoming) | vLLM + FP8 |
| Training (upcoming) | Unsloth + QLoRA + GRPO |

---

## Roadmap

### ✅ Sprint 1 — MVP (Done)
- Perception Layer — Qwen2.5-VL OCR
- SymPy Verification Layer
- CLI Pipeline

### 🔄 Sprint 2 — Cognitive Layer (Next)
- DeepSeek-R1-Distill-70B integration
- Chain-of-Thought reasoning
- `<think>` trace generation

### 📅 Sprint 3 — Training
- QLoRA + Unsloth SFT on OpenR1-Math-220K
- GRPO Reinforcement Learning loop
- Reward functions: correctness + format + execution

### 📅 Sprint 4 — Full System
- Process Reward Model (PRM)
- Streamlit Web UI
- FastAPI backend
- Docker deployment

---

## Datasets (Training)

| Dataset | Size | Purpose |
|---------|------|---------|
| OpenR1-Math-220K | 220K problems | Reasoning traces (DeepSeek-R1 distilled) |
| NuminaMath 1.5 | 900K problems | Competition math (AIME, Olympiad) |
| Synthetic TIR | 5K problems | Tool-Integrated Reasoning format |

---

## Key Concepts

- **System 2 Thinking** — Deep reasoning with self-correction vs fast pattern matching
- **MoE (Mixture of Experts)** — 256 routed experts, 8 active per token
- **MLA (Multi-Head Latent Attention)** — 93% KV cache reduction
- **GRPO** — Reinforcement Learning without Critic model
- **TIR (Tool-Integrated Reasoning)** — Model generates Python code for calculations
- **PRM (Process Reward Model)** — Verifies every intermediate reasoning step
- **QLoRA** — 4-bit quantized fine-tuning with LoRA adapters

---

## Contributing

This is an active project — modules are being added sprint by sprint.  
Feel free to open issues or PRs!

---

## License

Apache 2.0 — Free for commercial and personal use.

---

## References

1. DeepSeek-AI, "DeepSeek-R1", 2025
2. Qwen Team, "Qwen2.5-VL Technical Report", 2025
3. OpenAI, "Learning to Reason with LLMs" (o1), 2024
4. NuminaMath Team, "NuminaMath 1.5", 2024
5. Unsloth AI, github.com/unslothai/unsloth, 2025
6. HuggingFace, "OpenR1-Math-220K", 2025
7. DeepSeek-AI, "DeepSeek-V3 Technical Report", 2024
8. Goyal R., "MathMind 2.0 Technical Report", January 2026
