"""
stego_facade.py
================
Unified Steganography Facade Module supporting both:
1. "coltuc_pee": Coltuc 2x2 Low-Distortion PEE (Spatial Domain)
2. "zhang_zeng_ou_hs": Zhang-Zeng-Ou 2D HS + Matrix Embedding (Signal Processing 2026 SOTA)
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, ".."))

if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

HEVC_RDH_DIR = os.path.join(_PROJECT_ROOT, "hevc_rdh")
if HEVC_RDH_DIR not in sys.path:
    sys.path.insert(0, HEVC_RDH_DIR)

import pee_stego

try:
    import hevc_rdh_core
    HAS_HEVC_RDH = True
except Exception as e:
    HAS_HEVC_RDH = False
    print(f"⚠️ Warning: HEVC RDH core (Zhang-Zeng-Ou 2D HS) load warning: {e}")

ALGORITHMS = {
    "coltuc_pee": {
        "name": "Coltuc 2x2 Low-Distortion PEE",
        "description": "空間域 2x2 低失真預測誤差擴張法 (超高速、高容量、通用所有視訊格式)",
        "module": pee_stego
    },
    "zhang_zeng_ou_hs": {
        "name": "Zhang-Zeng-Ou 2D HS (Signal Processing 2026)",
        "description": "Elsevier 頂刊 2D QDST 直方圖位移 + (1,7,3) 矩陣嵌入法 (中低容量超高 PSNR 畫質)",
        "module": hevc_rdh_core if HAS_HEVC_RDH else pee_stego
    }
}

def estimate_capacity(video_path, method="coltuc_pee"):
    """Estimates usable secret payload capacity (in bytes) for the chosen method."""
    if method == "zhang_zeng_ou_hs" and HAS_HEVC_RDH:
        return hevc_rdh_core.estimate_capacity(video_path)
    return pee_stego.estimate_capacity(video_path)

def get_payload_size(file_paths):
    """Calculates total packaged secret payload size in bytes."""
    return pee_stego.get_payload_size(file_paths)

def encode_video_multi(video_path, file_paths, output_path, method="coltuc_pee", chunked=True, initial_sec=6.0, progress_callback=None):
    """
    Encodes secret files into cover video using specified algorithm method.
    Supports chunked audio streaming (manifest pre-position + initial segment) by default.
    """
    print(f"🚀 [StegoFacade] Starting encoding using method: '{method}' (Chunked={chunked}, {initial_sec}s)")
    if method == "zhang_zeng_ou_hs" and HAS_HEVC_RDH:
        return hevc_rdh_core.encode_video_multi(video_path, file_paths, output_path, progress_callback=progress_callback)
    else:
        return pee_stego.encode_video_multi(video_path, file_paths, output_path, chunked=chunked, initial_sec=initial_sec, progress_callback=progress_callback)

def decode_video_multi(stego_video_path, output_dir, method="auto", progress_callback=None, on_manifest_ready=None, on_chunk_ready=None):
    """
    Extracts secret files from stego video using specified or auto-detected algorithm method.
    Supports on_manifest_ready and on_chunk_ready streaming callbacks.
    """
    print(f"🚀 [StegoFacade] Starting decoding using method: '{method}'...")

    if method == "zhang_zeng_ou_hs":
        if HAS_HEVC_RDH:
            return hevc_rdh_core.decode_video_multi(stego_video_path, output_dir, progress_callback=progress_callback)
        else:
            return pee_stego.decode_video_multi(stego_video_path, output_dir, progress_callback=progress_callback, on_manifest_ready=on_manifest_ready, on_chunk_ready=on_chunk_ready)

    elif method == "coltuc_pee":
        return pee_stego.decode_video_multi(stego_video_path, output_dir, progress_callback=progress_callback, on_manifest_ready=on_manifest_ready, on_chunk_ready=on_chunk_ready)

    else:
        # "auto" detection mode: try Coltuc PEE first; if failed, try Zhang-Zeng-Ou 2D HS
        try:
            print("  🔍 Auto-detecting algorithm: Trying Coltuc 2x2 PEE extraction...")
            res = pee_stego.decode_video_multi(stego_video_path, output_dir, progress_callback=progress_callback, on_manifest_ready=on_manifest_ready, on_chunk_ready=on_chunk_ready)
            if res:
                print("  ✓ Successfully extracted payload via Coltuc 2x2 PEE!")
                return res
        except Exception as err_pee:
            print(f"  ℹ️ Coltuc 2x2 PEE extraction attempt info: {err_pee}")

        if HAS_HEVC_RDH:
            try:
                print("  🔍 Auto-detecting algorithm: Trying Zhang-Zeng-Ou 2D HS extraction...")
                res_hs = hevc_rdh_core.decode_video_multi(stego_video_path, output_dir, progress_callback=progress_callback)
                if res_hs:
                    print("  ✓ Successfully extracted payload via Zhang-Zeng-Ou 2D HS!")
                    return res_hs
            except Exception as err_hs:
                print(f"  ❌ Zhang-Zeng-Ou 2D HS extraction failed: {err_hs}")

        # Fallback to standard PEE
        return pee_stego.decode_video_multi(stego_video_path, output_dir, progress_callback=progress_callback)
