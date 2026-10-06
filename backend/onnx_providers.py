"""Pick ONNX Runtime execution providers that can actually load on this machine.

onnxruntime-gpu reports CUDAExecutionProvider as "available" whenever its own
provider DLL is shipped, even when CUDA / cuDNN are not installed. Asking for it
then makes every session creation log a red error ("cublasLt64_13.dll ... is
missing") before silently falling back to CPU. Probing first keeps GPU support
for machines that have CUDA and keeps the log clean for those that do not.
"""
from __future__ import annotations

import ctypes
import os
import sys

_cuda_ok: bool | None = None

# LoadLibraryEx flag: resolve the DLL's dependencies from its own folder first and
# then the normal search path (incl. PATH) - the same way onnxruntime loads it.
_LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008


def cuda_usable() -> bool:
    """True when the CUDA provider and the CUDA libraries it depends on load."""
    global _cuda_ok
    if _cuda_ok is not None:
        return _cuda_ok
    _cuda_ok = False
    try:
        import onnxruntime as ort
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            return False
        capi = os.path.join(os.path.dirname(ort.__file__), "capi")
        if sys.platform == "win32":
            ctypes.WinDLL(os.path.join(capi, "onnxruntime_providers_cuda.dll"),
                          winmode=_LOAD_WITH_ALTERED_SEARCH_PATH)
        else:
            ctypes.CDLL(os.path.join(capi, "libonnxruntime_providers_cuda.so"))
        _cuda_ok = True
    except Exception:
        _cuda_ok = False
    return _cuda_ok


def onnx_providers() -> list[str]:
    """Providers to pass to InferenceSession / fastembed: GPU first when usable."""
    return (["CUDAExecutionProvider"] if cuda_usable() else []) + ["CPUExecutionProvider"]
