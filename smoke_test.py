"""Smoke test: import + minimal GPU op for every compiled component."""
import sys
import traceback

RESULTS = []


def check(name, fn):
    try:
        detail = fn()
        RESULTS.append((name, "OK", detail or ""))
    except Exception as e:
        RESULTS.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        traceback.print_exc()


import torch  # noqa: E402


def t_torch():
    assert torch.cuda.is_available(), "CUDA not available in torch"
    x = torch.rand(1000, 3, device="cuda")
    return (f"{torch.__version__} cuda={torch.version.cuda} "
            f"dev={torch.cuda.get_device_name(0)} sum={x.sum().item():.1f}")


check("torch+cuda", t_torch)
check("diff_gaussian_rasterization", lambda: __import__("diff_gaussian_rasterization") and "")
check("diff_gaussian_rasterization_ms._C", lambda: __import__("diff_gaussian_rasterization_ms._C") and "")
check("diff_gaussian_rasterization_ours", lambda: __import__("diff_gaussian_rasterization_ours") and "")
check("diff_gaussian_rasterization_sof", lambda: __import__("diff_gaussian_rasterization_sof") and "")


def t_simple_knn():
    from simple_knn._C import distCUDA2
    pts = torch.rand(2048, 3, device="cuda")
    d = distCUDA2(pts)
    assert d.shape[0] == 2048 and torch.isfinite(d).all()
    return f"distCUDA2 mean={d.mean().item():.5f}"


check("simple_knn distCUDA2", t_simple_knn)


def t_fused_ssim():
    from fused_ssim import fused_ssim
    a = torch.rand(1, 3, 128, 128, device="cuda", requires_grad=True)
    b = torch.rand(1, 3, 128, 128, device="cuda")
    for pad in ("same", "valid"):
        v = fused_ssim(a, b, padding=pad)
        v.backward()
        assert a.grad is not None
        a.grad = None
    return "forward+backward OK"


check("fused_ssim fwd/bwd", t_fused_ssim)
check("warp_patch_ncc", lambda: __import__("warp_patch_ncc") and "")


def t_nvdiffrast():
    import nvdiffrast.torch as dr
    ctx = dr.RasterizeCudaContext()  # first call JIT-compiles the plugin
    verts = torch.tensor([[[-0.5, -0.5, 0.0, 1.0], [0.5, -0.5, 0.0, 1.0],
                           [0.0, 0.5, 0.0, 1.0]]], device="cuda")
    tris = torch.tensor([[0, 1, 2]], dtype=torch.int32, device="cuda")
    rast, _ = dr.rasterize(ctx, verts, tris, resolution=[64, 64])
    cov = (rast[..., 3] > 0).float().mean().item()
    assert cov > 0.05
    return f"CUDA ctx rasterize coverage={cov:.3f}"


check("nvdiffrast JIT+rasterize", t_nvdiffrast)


def t_tetranerf():
    from tetranerf.utils.extension import cpp
    pts = torch.rand(500, 3, device="cuda")
    tets = cpp.triangulate(pts)
    assert tets.shape[1] == 4 and tets.shape[0] > 100
    return f"triangulate 500 pts -> {tets.shape[0]} tets"


check("tetranerf triangulate", t_tetranerf)


def t_scipy_delaunay():
    import numpy as np
    from scipy.spatial import Delaunay
    tets = Delaunay(np.random.rand(500, 3)).simplices
    return f"scipy Delaunay fallback -> {tets.shape[0]} tets"


check("scipy Delaunay fallback", t_scipy_delaunay)

print()
print("=" * 64)
w = max(len(n) for n, _, _ in RESULTS)
fails = 0
for name, status, detail in RESULTS:
    print(f"{name:<{w}}  {status:<5} {detail}")
    if status == "FAIL":
        fails += 1
print("=" * 64)
print(f"SMOKE TEST: {len(RESULTS) - fails}/{len(RESULTS)} passed")
sys.exit(1 if fails else 0)
