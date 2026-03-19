"""
Vision Service — computer vision analysis for Mars greenhouse plots.

Provides:
  SyntheticImageGenerator — renders a simulated camera image per plot state
  OpenCVPreprocessor      — preprocessing pipeline (blur, normalize) → base64 JPEG
  VisionService           — orchestrates image gen + Claude Vision via Bedrock

At high sim speeds (use_fast=True), CV is bypassed entirely and existing
simulation health values pass through unchanged.
"""
import base64
import io
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Stress flags that the simulation recognises
VALID_STRESS_FLAGS = {"disease", "water_stress", "radiation_shielding", "nutrient_deficiency"}

# Same model used by all other agents
_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
_REGION = "us-west-2"


# ---------------------------------------------------------------------------
# SyntheticImageGenerator
# ---------------------------------------------------------------------------

class SyntheticImageGenerator:
    """
    Renders a 224×224 PIL image representing a plot's visual health state.
    Used as a simulated camera feed until real imaging hardware is available.

    Images are seeded by (plot_id + last_cv_analysis_sol) so each Sol produces
    slightly different images even for the same plot, giving Claude Vision
    something genuine to analyse rather than perfectly circular feedback.
    """

    SIZE = 224

    # Base colours in RGB per crop type
    _CROP_COLORS = {
        "potato":       (139, 90,  43),
        "beans":        (34,  85,  34),
        "lettuce":      (100, 180, 60),
        "radish":       (220, 80,  100),
        "herbs":        (80,  140, 80),
        "cherry_tomato": (200, 60, 40),
    }
    _DEAD_COLOR = (160, 130, 40)   # yellowed / dying

    def generate(self, plot: dict, env: dict, angle: str = "top_down") -> Image.Image:
        """Return a synthetic PIL Image for this plot."""
        crop        = plot.get("crop", "potato")
        health      = max(0.0, min(1.0, float(plot.get("health", 1.0))))
        stress_flags= plot.get("stress_flags", [])
        plot_id     = plot.get("plot_id", "plot_0")
        sol         = int(plot.get("last_cv_analysis_sol", 0))

        # Deterministic RNG seeded per plot+sol so images vary between Sols
        rng    = random.Random(hash(f"{plot_id}_{sol}") & 0xFFFFFFFF)
        np_rng = np.random.RandomState(rng.randint(0, 2**31 - 1))

        # Interpolate plant colour: healthy base → dead/yellow as health falls
        br, bg, bb = self._CROP_COLORS.get(crop, (80, 120, 60))
        dr, dg, db = self._DEAD_COLOR
        r = int(br * health + dr * (1 - health))
        g = int(bg * health + dg * (1 - health))
        b = int(bb * health + db * (1 - health))

        # Canvas — dark soil background
        img = np.zeros((self.SIZE, self.SIZE, 3), dtype=np.uint8)
        img[:] = [15, 20, 12]

        # Plant body — filled ellipse; area shrinks slightly with poor health
        cx, cy = self.SIZE // 2, self.SIZE // 2
        rx = int(70 + health * 30)        # 70 – 100 px horizontal radius
        ry = int(rx * 0.65)
        cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, (r, g, b), -1)

        # Fine texture noise (seeded)
        noise = np_rng.randint(-15, 15, img.shape, dtype=np.int16)
        img   = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Angle-specific perspective transforms
        if angle == "side_left":
            # Tall narrow profile — compress horizontally, stretch vertically
            plant_region = img[cy - ry: cy + ry, cx - rx: cx + rx].copy()
            if plant_region.size > 0:
                h, w = plant_region.shape[:2]
                narrow = cv2.resize(plant_region, (max(1, w // 3), h))
                x1, x2 = cx - rx // 3, cx + rx // 3
                target_w = x2 - x1
                if target_w > 0:
                    img[cy - ry: cy + ry, x1:x2] = cv2.resize(narrow, (target_w, h))
            # Add vertical stem line
            cv2.line(img, (cx, cy + ry), (cx, max(0, cy - ry - 20)), (r // 2, g // 2, b // 2), 3)
        elif angle == "close_up":
            # Zoom into centre quarter — replicate the centre 112×112 to full 224×224
            half = self.SIZE // 4
            centre = img[cy - half: cy + half, cx - half: cx + half].copy()
            if centre.shape[0] > 0 and centre.shape[1] > 0:
                img = cv2.resize(centre, (self.SIZE, self.SIZE), interpolation=cv2.INTER_LINEAR)
        elif angle == "ground_level":
            # Low-angle view: compress top half, reveal soil at bottom
            top_half = img[: self.SIZE // 2, :].copy()
            img[: self.SIZE // 3, :] = cv2.resize(top_half, (self.SIZE, self.SIZE // 3))
            # Soil strip at bottom
            soil_color = np.array([40, 28, 15], dtype=np.uint8)
            img[self.SIZE * 3 // 4:, :] = soil_color
            # Moisture effect: slightly darker soil if high moisture

        # --- Stress flag visual effects ---

        if "disease" in stress_flags:
            # Dark irregular blotches
            n = rng.randint(6, 15)
            for _ in range(n):
                x = rng.randint(max(0, cx - rx + 5), min(self.SIZE - 1, cx + rx - 5))
                y = rng.randint(max(0, cy - ry + 5), min(self.SIZE - 1, cy + ry - 5))
                cv2.circle(img, (x, y), rng.randint(6, 18), (35, 55, 15), -1)

        if "water_stress" in stress_flags:
            # Brownish wilting gradient from top (leaves droop / dry out)
            for row in range(self.SIZE // 2):
                f = (self.SIZE // 2 - row) / (self.SIZE // 2) * 0.55
                img[row] = np.clip(
                    img[row].astype(np.float32) * (1 - f) + np.array([80, 55, 20]) * f,
                    0, 255,
                ).astype(np.uint8)

        if "radiation_shielding" in stress_flags:
            # Reddish-purple discolouration overlay
            overlay = np.zeros_like(img)
            overlay[:, :, 0] = 90          # channel 0 = R in our RGB convention
            img = cv2.addWeighted(img, 0.72, overlay, 0.28, 0)

        if "nutrient_deficiency" in stress_flags:
            # Yellow-brown spots (chlorosis)
            n = rng.randint(4, 10)
            for _ in range(n):
                x = rng.randint(max(0, cx - rx + 10), min(self.SIZE - 1, cx + rx - 10))
                y = rng.randint(max(0, cy - ry + 10), min(self.SIZE - 1, cy + ry - 10))
                cv2.circle(img, (x, y), rng.randint(8, 16), (130, 110, 35), -1)

        # img channels are ordered R,G,B (we filled them that way); PIL fromarray expects RGB
        return Image.fromarray(img)


# ---------------------------------------------------------------------------
# OpenCVPreprocessor
# ---------------------------------------------------------------------------

class OpenCVPreprocessor:
    """
    Applies a standard preprocessing pipeline to a PIL image and returns a
    base64-encoded JPEG string suitable for passing to Claude Vision.

    Pipeline: PIL RGB → BGR → GaussianBlur → normalize → RGB → JPEG base64
    """

    def preprocess(self, image: Image.Image) -> str:
        # PIL RGB → numpy → BGR for OpenCV
        img_rgb = np.array(image)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        # Denoise
        img_bgr = cv2.GaussianBlur(img_bgr, (3, 3), 0)

        # Normalise brightness range
        img_bgr = cv2.normalize(img_bgr, None, 0, 255, cv2.NORM_MINMAX)

        # BGR → RGB for PIL encoding
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # JPEG encode → base64 string
        buffer = io.BytesIO()
        Image.fromarray(img_rgb).save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode()


# ---------------------------------------------------------------------------
# VisionService
# ---------------------------------------------------------------------------

class VisionService:
    """
    Orchestrates synthetic image generation, OpenCV preprocessing, and
    Claude Vision analysis via AWS Bedrock.

    On any Bedrock / parsing failure the current simulation health is returned
    unchanged so the simulation never crashes due to CV errors.
    """

    def __init__(self, bedrock_client=None):
        # Accepts a pre-built boto3 bedrock-runtime client (useful for testing)
        self._client = bedrock_client

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=_REGION)
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_plot(
        self,
        plot: dict,
        env: dict,
        image: Image.Image = None,
    ) -> dict:
        """
        Analyse a single plot with Claude Vision.

        Returns:
            {
                "plot_id":      str,
                "health_score": float 0–1,
                "confidence":   float 0–1,
                "stress_flags": list[str],
                "cv_reasoning": str,
                "kb_fallback":  bool,   # True → Bedrock call failed
            }
        """
        plot_id = plot.get("plot_id", "unknown")
        crop    = plot.get("crop", "unknown")

        try:
            if image is None:
                image = SyntheticImageGenerator().generate(plot, env)

            base64_img = OpenCVPreprocessor().preprocess(image)

            prompt = (
                f"You are a Mars greenhouse plant health inspector.\n"
                f"Crop type: {crop}\n"
                f"Known stress conditions: disease (dark spots/lesions), "
                f"water_stress (wilting/browning from top), "
                f"radiation_shielding (reddish discolouration), "
                f"nutrient_deficiency (yellow-brown chlorosis spots).\n\n"
                f"Analyse this plant image carefully and return ONLY valid JSON "
                f"with no surrounding text:\n"
                f'{{"health_score": <float 0.0-1.0>, '
                f'"confidence": <float 0.0-1.0>, '
                f'"stress_flags": [<list of detected conditions from the known set>], '
                f'"reasoning": "<one sentence explanation>"}}\n\n'
                f"health_score 1.0 = perfectly healthy, 0.0 = dying. "
                f"Only include stress_flags that are clearly visible in the image."
            )

            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 256,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_img,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            })

            response    = self._get_client().invoke_model(modelId=_MODEL_ID, body=body)
            result_body = json.loads(response["body"].read())
            text        = result_body["content"][0]["text"].strip()
            parsed      = self._parse_json(text)

            flags = [f for f in parsed.get("stress_flags", []) if f in VALID_STRESS_FLAGS]

            return {
                "plot_id":      plot_id,
                "health_score": max(0.0, min(1.0, float(parsed.get("health_score", plot.get("health", 1.0))))),
                "confidence":   max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
                "stress_flags": flags,
                "cv_reasoning": parsed.get("reasoning", ""),
                "kb_fallback":  False,
            }

        except Exception as exc:
            logger.warning("VisionService.analyze_plot failed for %s: %s", plot_id, exc)
            return {
                "plot_id":      plot_id,
                "health_score": float(plot.get("health", 1.0)),
                "confidence":   0.0,
                "stress_flags": list(plot.get("stress_flags", [])),
                "cv_reasoning": f"CV analysis failed: {exc}",
                "kb_fallback":  True,
            }

    def analyze_all_plots(
        self,
        plots: list,
        env: dict,
        use_fast: bool = False,
    ) -> dict:
        """
        Analyse a list of plots, returning {plot_id: result}.

        use_fast=True  → skip Bedrock entirely, return passthrough results
                          instantly (used at sim_speed > 5x).
        Otherwise      → parallel Bedrock calls via ThreadPoolExecutor(5).
        """
        if use_fast:
            return {
                p["plot_id"]: {
                    "plot_id":      p["plot_id"],
                    "health_score": float(p.get("health", 1.0)),
                    "confidence":   0.0,
                    "stress_flags": list(p.get("stress_flags", [])),
                    "cv_reasoning": "Fast mode — CV skipped.",
                    "kb_fallback":  True,
                }
                for p in plots
            }

        results = {}
        with ThreadPoolExecutor(max_workers=min(5, len(plots))) as executor:
            future_to_id = {
                executor.submit(self.analyze_plot, plot, env): plot["plot_id"]
                for plot in plots
            }
            for future in as_completed(future_to_id):
                pid = future_to_id[future]
                try:
                    results[pid] = future.result()
                except Exception as exc:
                    logger.warning("CV parallel execution failed for %s: %s", pid, exc)
                    plot = next((p for p in plots if p["plot_id"] == pid), {})
                    results[pid] = {
                        "plot_id":      pid,
                        "health_score": float(plot.get("health", 1.0)),
                        "confidence":   0.0,
                        "stress_flags": list(plot.get("stress_flags", [])),
                        "cv_reasoning": f"Parallel execution failed: {exc}",
                        "kb_fallback":  True,
                    }
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract a JSON object from Claude's response text."""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {}
