# Makefile

PYTHON_VERSION := 3.12
PIP := pip$(PYTHON_VERSION)

install_dependencies:
	@echo "Upgrading pip..."
	@$(PIP) install --upgrade pip
	@echo "Installing torch-cpu..."
	@$(PIP) install torch==2.7.1+cpu --index-url https://download.pytorch.org/whl/cpu
	@echo "Installing other dependencies..."
	@$(PIP) install -r requirements.txt
	@echo "Done"

.PHONY: install_dependencies
