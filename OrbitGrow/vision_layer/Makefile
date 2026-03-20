LAYER_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_DIR := $(abspath $(LAYER_DIR)..)

build-OrbitGrowVisionLayer:
	pip install -r $(LAYER_DIR)requirements.txt -t "$(ARTIFACTS_DIR)/python" --platform manylinux2014_x86_64 --implementation cp --python-version 3.11 --only-binary=:all:
	mkdir -p "$(ARTIFACTS_DIR)/python/agents"
	cp $(REPO_DIR)/agents/__init__.py "$(ARTIFACTS_DIR)/python/agents/" 2>/dev/null || touch "$(ARTIFACTS_DIR)/python/agents/__init__.py"
	cp $(REPO_DIR)/agents/vision_service.py "$(ARTIFACTS_DIR)/python/agents/vision_service.py"
	# Aggressive cleanup to stay under 250 MB
	find "$(ARTIFACTS_DIR)/python" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -name "*.pyc" -delete 2>/dev/null || true
	rm -rf "$(ARTIFACTS_DIR)/python/numpy/core/tests" "$(ARTIFACTS_DIR)/python/numpy/lib/tests" 2>/dev/null || true
	rm -rf "$(ARTIFACTS_DIR)/python/cv2/data" 2>/dev/null || true
