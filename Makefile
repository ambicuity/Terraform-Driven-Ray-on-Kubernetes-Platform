# Developer Entry Point
#
# Usage:
#   make help       - Show this help message
#   make lint       - Run deterministic local static checks
#   make test       - Run deterministic local validation and tests
#   make validate   - Validate Terraform root and example stacks
#   make evidence   - Generate the committed local evidence bundle
#   make clean      - Clean up local Terraform state and test artifacts

TERRAFORM := $(if $(wildcard ./.tmp-tools/bin/terraform-1.9.8),./.tmp-tools/bin/terraform-1.9.8,terraform)
OPA := $(if $(wildcard ./.tmp-tools/bin/opa-0.63.0),./.tmp-tools/bin/opa-0.63.0,opa)

.PHONY: help lint test validate evidence clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run deterministic static checks (Terraform fmt, Helm, Actions, shell)
	@echo "--- Terraform fmt ---"
	@$(TERRAFORM) fmt -check -recursive terraform/
	@echo "--- Helm lint ---"
	@helm lint helm/ray
	@echo "--- Helm render ---"
	@helm template ray-ci helm/ray >/tmp/ray-rendered.yaml
	@echo "--- Actionlint ---"
	@actionlint -color
	@echo "--- Shellcheck ---"
	@shellcheck local_test.sh validation/*.sh tests/evidence/*.sh
	@echo "--- Python compileall ---"
	@python3 -m compileall scripts tests workloads validation
	@echo "--- OPA tests ---"
	@$(OPA) test policies -v

test: ## Run local validation and tests
	@echo "--- Terraform root ---"
	@$(TERRAFORM) -chdir=terraform init -backend=false
	@$(TERRAFORM) -chdir=terraform validate
	@$(TERRAFORM) -chdir=terraform test
	@echo "--- Terraform example ---"
	@$(TERRAFORM) -chdir=terraform/examples/complete init -backend=false
	@$(TERRAFORM) -chdir=terraform/examples/complete validate
	@echo "--- Python tests ---"
	@pytest tests/ -q

evidence: ## Generate the committed local evidence bundle
	@bash tests/evidence/run_local_evidence.sh

validate: ## Validate Terraform root and example stacks
	@$(TERRAFORM) -chdir=terraform init -backend=false
	@$(TERRAFORM) -chdir=terraform validate
	@$(TERRAFORM) -chdir=terraform/examples/complete init -backend=false
	@$(TERRAFORM) -chdir=terraform/examples/complete validate

clean: ## Clean up temporary files
	@find . -type d -name ".terraform" -exec rm -rf {} +
	@find . -type f -name "*.tfstate*" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@rm -rf reports/
	@rm -f coverage.xml test-results.xml
