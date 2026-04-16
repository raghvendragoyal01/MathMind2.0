"""
api.py — MathMind 2.0 FastAPI Layer
===================================
Provides a stateless, RESTful interface for the MathMind pipeline.
Implements a strict asyncio lock to prevent GPU OOM.
Implements a multiprocessing sandbox with SIGKILL for SymPy timeouts.
"""

import io
import asyncio
import multiprocessing as mp
from contextlib import asynccontextmanager  # <--- ADD THIS LINE HERE
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, List
from PIL import Image

# macOS compatibility for multiprocessing
try:
    mp.set_start_method("spawn", force=True)
except RuntimeError:
    pass

# Import your existing MathMind modules
from ocr_engine import MathOCREngine
from sympy_verifier import verify_latex, report_to_dict

# ── Initialization & State ───────────────────────────────────────────────────

gpu_lock = asyncio.Lock()
engine = MathOCREngine(verbose=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting MathMind 2.0 API...")
    engine.load()
    yield
    print("🛑 Shutting down MathMind 2.0 API...")

app = FastAPI(
    title="MathMind 2.0 API",
    description="Neuro-Symbolic Math OCR and Verification Pipeline",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Models ──────────────────────────────────────────────────────────

class Solution(BaseModel):
    variable: str
    values: List[str]

class EquationResult(BaseModel):
    raw_latex: str
    sympy_form: Optional[str]
    status: str
    confidence: float
    solutions: List[Solution] = []

class VerificationData(BaseModel):
    total_equations: int
    parsed_ok: int
    verified_ok: int
    overall_confidence: float
    details: List[EquationResult]

class MathMindResponse(BaseModel):
    success: bool
    input_type: str
    tokens_generated: int
    latex: str
    verification: Optional[VerificationData] = None
    error: Optional[str] = None

# ── SymPy Sandbox (Timeout Protection) ───────────────────────────────────────

def _verification_worker(latex: str, result_queue: mp.Queue):
    """Runs in a totally isolated child process."""
    try:
        report = verify_latex(latex, verbose=False)
        result_queue.put({"success": True, "data": report_to_dict(report)})
    except Exception as e:
        result_queue.put({"success": False, "error": f"SymPy Crash: {str(e)}"})

async def verify_with_hard_timeout(latex: str, timeout: float = 5.0) -> dict:
    """Spawns a process to verify math. Ruthlessly kills it if it exceeds timeout."""
    result_queue = mp.Queue()
    proc = mp.Process(target=_verification_worker, args=(latex, result_queue))
    proc.start()
    
    def _wait():
        proc.join(timeout=timeout)
        if proc.is_alive():
            print(f"⏱️ SymPy Timeout! Killing runaway process {proc.pid}...")
            proc.terminate() # SIGTERM
            proc.join(timeout=1.0)
            if proc.is_alive():
                proc.kill()  # SIGKILL
            return {"success": False, "error": f"Verification timed out after {timeout}s"}
        
        if not result_queue.empty():
            return result_queue.get_nowait()
        return {"success": False, "error": "Worker crashed without returning data."}
    
    return await run_in_threadpool(_wait)

# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "online", "gpu_locked": gpu_lock.locked()}

@app.post("/api/v1/solve", response_model=MathMindResponse)
async def process_math_image(
    file: UploadFile = File(...),
    input_type: str = Form("auto"),
    verify: bool = Form(True)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # 1. Perception Layer (Protected by GPU Lock)
        async with gpu_lock:
            print(f"🔒 GPU Lock acquired for {file.filename}")
            ocr_result = await run_in_threadpool(
                engine.transcribe, 
                image=image, 
                input_type=input_type
            )
            print(f"🔓 GPU Lock released for {file.filename}")

        latex_output = ocr_result["latex"]
        verification_payload = None
        api_error = None

        # 2. Verification Layer (Protected by Multiprocessing Sandbox)
        if verify:
            worker_result = await verify_with_hard_timeout(latex_output, timeout=5.0)
            
            if not worker_result["success"]:
                # If SymPy crashed or timed out, we catch it gracefully!
                api_error = worker_result["error"]
            else:
                report_dict = worker_result["data"]
                eq_details = []
                
                for eq in report_dict["equations"]:
                    
                    if eq["verification"] is True:
                        status = "Identity"
                    elif eq["solutions"]:
                        status = "Solved"
                    elif eq["error"]:
                        status = "Error"
                    elif eq["sympy_expr"] is not None: 
                        status = "Parsed"
                    else:
                        status = "Failed"

                    formatted_sols = [
                        Solution(variable=k, values=v) for k, v in eq["solutions"].items()
                    ]

                    eq_details.append(EquationResult(
                        raw_latex=eq["raw_latex"],
                        sympy_form=eq["sympy_expr"],
                        status=status,
                        confidence=eq["confidence"],
                        solutions=formatted_sols
                    ))

                verification_payload = VerificationData(
                    total_equations=report_dict["total"],
                    parsed_ok=report_dict["parsed_ok"],
                    verified_ok=report_dict["verified_ok"],
                    overall_confidence=report_dict["overall_confidence"],
                    details=eq_details
                )

        return MathMindResponse(
            success=True,
            input_type=ocr_result["input_type"],
            tokens_generated=ocr_result["tokens_generated"],
            latex=latex_output,
            verification=verification_payload,
            error=api_error # Will populate if a timeout occurred, but keep success=True because OCR worked!
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error processing request: {e}")
        return MathMindResponse(
            success=False,
            input_type=input_type,
            tokens_generated=0,
            latex="",
            error=str(e)
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)