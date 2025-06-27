# Makefile

PYTHON_VERSION := $(shell cat .python-version | cut -d. -f1,2)
PIP := pip$(PYTHON_VERSION)
ALEMBIC_PATH := app/db/migrations

# Python packages install command
install_dependencies:
	@echo "Upgrading pip..."
	@$(PIP) install --upgrade pip
	@echo "Installing torch-cpu..."
	@$(PIP) install torch==2.7.1+cpu --index-url https://download.pytorch.org/whl/cpu
	@echo "Installing other dependencies..."
	@$(PIP) install -r requirements.txt
	@echo "Done"

# Database migration commands
migration-setup:
	@if [ -f "$(ALEMBIC_PATH)/alembic.ini" ]; then \
		echo "Error: Alembic already initialized! Found $(ALEMBIC_PATH)/alembic.ini"; \
		echo "Use other migration-* commands for existing setup."; \
		exit 1; \
	else \
		echo "Initializing alembic in $(ALEMBIC_PATH)..."; \
		alembic init $(ALEMBIC_PATH); \
		echo "Alembic initialized successfully!"; \
	fi

migration-current:
	@alembic -c $(ALEMBIC_PATH)/alembic.ini current

migration-history:
	@alembic -c $(ALEMBIC_PATH)/alembic.ini history

migration-upgrade:
	@alembic -c $(ALEMBIC_PATH)/alembic.ini upgrade head

migration-downgrade:
	@alembic -c $(ALEMBIC_PATH)/alembic.ini downgrade -1

migration-revision:
	@alembic -c $(ALEMBIC_PATH)/alembic.ini revision --autogenerate -m "$(MSG)"

migration-heads:
	@alembic -c $(ALEMBIC_PATH)/alembic.ini heads

.PHONY: install_dependencies migration-setup migration-current migration-history migration-upgrade migration-downgrade migration-revision migration-heads
