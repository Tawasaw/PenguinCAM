.PHONY: install test

install:
	@command -v uv >/dev/null 2>&1 || { echo "Installing uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh; }
	@echo "Installing dependencies from requirements.txt..."
	uv pip install -r requirements.txt

test:
	@echo "Running unit tests..."
	@PENGUINCAM_STRICT_GCODE=1 uv run python -m unittest discover -s tests -t . --buffer
	@echo ""
	@echo "Running system tests..."
	@PENGUINCAM_STRICT_GCODE=1 uv run python gcode_test.py --quiet
