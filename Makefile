# Developer Entry Point

.PHONY: help lint fmt test validate clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run all linters (tflint, checkov, flake8)
	@echo "--- Running TFLint ---"
	@cd terraform && tflint --init && tflint
	@echo "--- Running Checkov ---"
	@checkov -d terraform
	@echo "--- Running Flake8 (scripts) ---"
	@flake8 scripts/
	@echo "--- Running Flake8 (workloads) ---"
	@flake8 workloads/

fmt: ## Format all files (terraform, python)
	@echo "--- Formatting Terraform ---"
	@terraform fmt -recursive terraform/
	@echo "--- Formatting Python ---"
	@black scripts/ workloads/

test: ## Run all tests (terraform test, pytest)
	@echo "--- Running Terraform Tests ---"
	@cd terraform && terraform init -backend=false && terraform test
	@echo "--- Running Python Tests ---"
	@pytest tests/

validate: ## Validate terraform configuration
	@echo "--- Validating Terraform ---"
	@cd terraform && terraform init -backend=false && terraform validate

clean: ## Clean up temporary files
	@find . -type d -name ".terraform" -exec rm -rf {} +
	@find . -type f -name "*.tfstate*" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@rm -rf reports/
