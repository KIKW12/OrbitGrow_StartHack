"""Unit tests for agents/vision_service.py"""
import sys
import os
import base64
import json
from unittest.mock import MagicMock, patch
from io import BytesIO

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.vision_service import (
    SyntheticImageGenerator,
    OpenCVPreprocessor,
    VisionService,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_HEALTHY_PLOT = {
    "plot_id": "potato_1",
    "crop": "potato",
    "health": 1.0,
    "stress_flags": [],
    "last_cv_analysis_sol": 5,
    "cv_confidence": 0.0,
}

_ENV = {
    "temperature_c": 22.0,
    "humidity_pct": 65.0,
    "co2_ppm": 1200.0,
    "light_umol": 400.0,
}


# ---------------------------------------------------------------------------
# SyntheticImageGenerator
# ---------------------------------------------------------------------------

def test_synthetic_image_returns_correct_size():
    gen = SyntheticImageGenerator()
    img = gen.generate(_HEALTHY_PLOT, _ENV)
    assert isinstance(img, Image.Image)
    assert img.size == (224, 224)


def test_synthetic_image_healthy_plot_is_not_black():
    gen = SyntheticImageGenerator()
    img = gen.generate(_HEALTHY_PLOT, _ENV)
    arr = np.array(img)
    # A healthy plant image should not be nearly black
    assert arr.mean() > 15


def test_synthetic_image_diseased_differs_from_healthy():
    gen = SyntheticImageGenerator()
    healthy  = gen.generate({**_HEALTHY_PLOT, "health": 1.0, "stress_flags": []}, _ENV)
    diseased = gen.generate({**_HEALTHY_PLOT, "health": 0.4, "stress_flags": ["disease"]}, _ENV)
    arr_h = np.array(healthy).astype(float)
    arr_d = np.array(diseased).astype(float)
    # Mean absolute difference should be meaningful
    assert np.mean(np.abs(arr_h - arr_d)) > 5


def test_synthetic_image_all_crops_generate_without_error():
    gen = SyntheticImageGenerator()
    for crop in ["potato", "beans", "lettuce", "radish", "herbs"]:
        img = gen.generate({**_HEALTHY_PLOT, "crop": crop}, _ENV)
        assert img.size == (224, 224)


def test_synthetic_image_all_stress_flags_generate_without_error():
    gen = SyntheticImageGenerator()
    plot = {
        **_HEALTHY_PLOT,
        "health": 0.5,
        "stress_flags": ["disease", "water_stress", "radiation_shielding", "nutrient_deficiency"],
    }
    img = gen.generate(plot, _ENV)
    assert img.size == (224, 224)


# ---------------------------------------------------------------------------
# OpenCVPreprocessor
# ---------------------------------------------------------------------------

def test_preprocessor_returns_valid_base64_jpeg():
    gen   = SyntheticImageGenerator()
    img   = gen.generate(_HEALTHY_PLOT, _ENV)
    pre   = OpenCVPreprocessor()
    result = pre.preprocess(img)

    assert isinstance(result, str)
    assert len(result) > 0

    decoded = base64.b64decode(result)
    # JPEG magic bytes: FF D8
    assert decoded[:2] == b"\xff\xd8"


def test_preprocessor_output_is_decodable_image():
    gen  = SyntheticImageGenerator()
    img  = gen.generate(_HEALTHY_PLOT, _ENV)
    pre  = OpenCVPreprocessor()
    b64  = pre.preprocess(img)

    decoded = base64.b64decode(b64)
    reopened = Image.open(BytesIO(decoded))
    assert reopened.size == (224, 224)


# ---------------------------------------------------------------------------
# VisionService — fallback behaviour
# ---------------------------------------------------------------------------

def _make_bedrock_response(health=0.85, confidence=0.9, flags=None, reasoning="looks good"):
    """Build a mock Bedrock response matching the Messages API format."""
    flags = flags or []
    payload = json.dumps({
        "health_score": health,
        "confidence":   confidence,
        "stress_flags": flags,
        "reasoning":    reasoning,
    })
    body_bytes = json.dumps({
        "content": [{"type": "text", "text": payload}],
    }).encode()

    mock_resp = MagicMock()
    mock_resp.__getitem__ = lambda self, key: (
        BytesIO(body_bytes) if key == "body" else None
    )
    return mock_resp


def test_vision_service_fallback_on_bedrock_failure():
    mock_client = MagicMock()
    mock_client.invoke_model.side_effect = Exception("Bedrock unavailable")

    vs   = VisionService(bedrock_client=mock_client)
    plot = {**_HEALTHY_PLOT, "health": 0.75, "stress_flags": ["water_stress"]}
    result = vs.analyze_plot(plot, _ENV)

    assert result["kb_fallback"] is True
    assert result["health_score"] == 0.75       # preserved from sim
    assert "water_stress" in result["stress_flags"]
    assert result["confidence"] == 0.0


def test_vision_service_returns_valid_result_on_success():
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_bedrock_response(
        health=0.8, confidence=0.9, flags=["disease"], reasoning="spotted lesions"
    )

    vs     = VisionService(bedrock_client=mock_client)
    result = vs.analyze_plot(_HEALTHY_PLOT, _ENV)

    assert result["kb_fallback"] is False
    assert 0.0 <= result["health_score"] <= 1.0
    assert 0.0 <= result["confidence"]   <= 1.0
    assert result["plot_id"] == "potato_1"


def test_vision_service_filters_invalid_stress_flags():
    """Claude Vision must not inject unknown flag names into the simulation."""
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_bedrock_response(
        flags=["disease", "unknown_flag", "another_bad_flag"]
    )

    vs     = VisionService(bedrock_client=mock_client)
    result = vs.analyze_plot(_HEALTHY_PLOT, _ENV)

    for f in result["stress_flags"]:
        assert f in {"disease", "water_stress", "radiation_shielding", "nutrient_deficiency"}


# ---------------------------------------------------------------------------
# VisionService — analyze_all_plots
# ---------------------------------------------------------------------------

def _make_plots(n=5):
    return [
        {**_HEALTHY_PLOT, "plot_id": f"potato_{i}", "health": 0.9}
        for i in range(n)
    ]


def test_analyze_all_plots_fast_mode_skips_bedrock():
    mock_client = MagicMock()
    vs = VisionService(bedrock_client=mock_client)

    results = vs.analyze_all_plots(_make_plots(5), _ENV, use_fast=True)

    mock_client.invoke_model.assert_not_called()
    assert len(results) == 5
    for r in results.values():
        assert r["confidence"] == 0.0
        assert r["kb_fallback"] is True


def test_analyze_all_plots_returns_all_plots():
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_bedrock_response()

    plots   = _make_plots(3)
    vs      = VisionService(bedrock_client=mock_client)
    results = vs.analyze_all_plots(plots, _ENV, use_fast=False)

    assert len(results) == 3
    for plot in plots:
        assert plot["plot_id"] in results
