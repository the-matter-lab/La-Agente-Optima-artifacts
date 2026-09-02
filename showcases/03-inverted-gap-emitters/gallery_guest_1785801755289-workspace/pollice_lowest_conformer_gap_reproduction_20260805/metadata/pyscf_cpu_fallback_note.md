# Local runtime note: PySCF CPU fallback patch

During a direct water smoke test, the local environment had `gpu4pyscf`/`cupy` importable but no CUDA-capable device. The PySCF workflow attempted `mf.to_gpu()` and failed with `cudaErrorNoDevice`. For local execution robustness, `/app/domains/pyscf/ontopyscf.py` was patched so `PyscfInput.pyscf_mf` catches any exception from `mf.to_gpu()` and falls back to the CPU mean-field object.

This patch is not part of the campaign package in this folder; it is documented here because it affects reproduction in CPU-only containers. On a fresh environment, either use a CUDA-capable GPU/gpu4pyscf setup, Modal GPU execution, or apply an equivalent CPU fallback.
