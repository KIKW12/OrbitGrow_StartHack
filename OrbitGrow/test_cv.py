"""
Standalone CV test — runs the full OpenCV + Claude Vision pipeline on a real image.
No server needed. Run with: .venv/bin/python test_cv.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))

from PIL import Image as PILImage
from agents.vision_service import VisionService, OpenCVPreprocessor, SyntheticImageGenerator

IMAGE_PATH = os.path.join(os.path.dirname(__file__), "test_plant.jpg")

# ---------------------------------------------------------------------------
# Step 1: Load and inspect the real image
# ---------------------------------------------------------------------------
print("\n=== Step 1: Load real image ===")
img = PILImage.open(IMAGE_PATH).convert("RGB")
print(f"  Original size : {img.width} x {img.height} px")

# Resize to max 1024 px (same as the server endpoint does)
max_dim = 1024
if max(img.width, img.height) > max_dim:
    img.thumbnail((max_dim, max_dim), PILImage.LANCZOS)
    print(f"  Resized to    : {img.width} x {img.height} px")

# ---------------------------------------------------------------------------
# Step 2: Run OpenCV preprocessing
# ---------------------------------------------------------------------------
print("\n=== Step 2: OpenCV preprocessing ===")
preprocessor = OpenCVPreprocessor()
b64 = preprocessor.preprocess(img)
print(f"  Base64 JPEG size : {len(b64):,} chars  ({len(b64) * 3 // 4 / 1024:.1f} KB)")
print("  GaussianBlur + normalize applied OK")

# Save the preprocessed version so you can inspect it
import base64, io
decoded = base64.b64decode(b64)
preprocessed_img = PILImage.open(io.BytesIO(decoded))
out_path = os.path.join(os.path.dirname(__file__), "test_plant_preprocessed.jpg")
preprocessed_img.save(out_path)
print(f"  Preprocessed image saved → {out_path}")

# ---------------------------------------------------------------------------
# Step 3: Compare with a synthetic image for the same plot
# ---------------------------------------------------------------------------
print("\n=== Step 3: Synthetic image (for comparison) ===")
gen = SyntheticImageGenerator()
sample_plot = {
    "plot_id": "potato_1",
    "crop": "potato",
    "health": 0.75,
    "stress_flags": ["nutrient_deficiency"],
    "last_cv_analysis_sol": 10,
}
synthetic = gen.generate(sample_plot, {})
syn_path = os.path.join(os.path.dirname(__file__), "test_plant_synthetic.jpg")
synthetic.save(syn_path)
print(f"  Synthetic image saved → {syn_path}")
print("  (This is what the sim normally sends to Claude)")

# ---------------------------------------------------------------------------
# Step 4: Call Claude Vision via Bedrock with the real image
# ---------------------------------------------------------------------------
print("\n=== Step 4: Claude Vision analysis (Bedrock) ===")
print("  Sending real image to Claude Vision...")

plot = {
    "plot_id": "potato_1",
    "crop": "potato",
    "health": 1.0,
    "stress_flags": [],
    "last_cv_analysis_sol": -1,
    "cv_confidence": 0.0,
}
env = {
    "temperature_c": 22.0,
    "humidity_pct": 65.0,
    "co2_ppm": 1200.0,
    "light_umol": 400.0,
}

vs = VisionService()
result = vs.analyze_plot(plot, env, image=img)

print()
print("  Result:")
print(json.dumps(result, indent=4))

if result["kb_fallback"]:
    print("\n  [!] kb_fallback=True — Bedrock call failed (check AWS credentials / region)")
else:
    print("\n  Claude Vision analysis successful!")
    print(f"  Health score : {result['health_score']:.2f}")
    print(f"  Confidence   : {result['confidence']:.0%}")
    print(f"  Stress flags : {result['stress_flags'] or 'none detected'}")
    print(f"  Reasoning    : {result['cv_reasoning']}")
