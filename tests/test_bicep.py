"""
Tests for Bicep infrastructure files
Validates syntax, linting, and basic structure of Bicep templates
"""

import subprocess
import pytest
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
INFRA_DIR = PROJECT_ROOT / "infra"

# Bicep files to test
BICEP_FILES = [
    INFRA_DIR / "main.bicep",
    INFRA_DIR / "ai-foundry.bicep",
    INFRA_DIR / "storage.bicep",
    INFRA_DIR / "container.bicep",
]


class TestBicepSyntax:
    """Test that all Bicep files have valid syntax"""

    @pytest.mark.parametrize("bicep_file", BICEP_FILES)
    def test_bicep_build(self, bicep_file):
        """Test that bicep files can be built successfully"""
        result = subprocess.run(
            ["az", "bicep", "build", "--file", str(bicep_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Bicep build failed for {bicep_file}:\n{result.stderr}"

    @pytest.mark.parametrize("bicep_file", BICEP_FILES)
    def test_bicep_lint(self, bicep_file):
        """Test that bicep files pass linting checks"""
        result = subprocess.run(
            ["az", "bicep", "lint", "--file", str(bicep_file)],
            capture_output=True,
            text=True,
        )
        # Lint returns 0 for success, may have warnings but no errors
        assert result.returncode == 0, f"Bicep lint found errors in {bicep_file}:\n{result.stderr}"


class TestMainBicep:
    """Tests specific to main.bicep"""

    def test_main_has_required_parameters(self):
        """Test that main.bicep has expected parameters"""
        bicep_file = INFRA_DIR / "main.bicep"
        content = bicep_file.read_text()
        
        assert "param location" in content, "main.bicep should have location parameter"
        assert "param prefix" in content, "main.bicep should have prefix parameter"

    def test_main_references_modules(self):
        """Test that main.bicep references the required modules"""
        bicep_file = INFRA_DIR / "main.bicep"
        content = bicep_file.read_text()
        
        assert "'storage.bicep'" in content, "main.bicep should reference storage.bicep"
        assert "'ai-foundry.bicep'" in content, "main.bicep should reference ai-foundry.bicep"

    def test_main_has_outputs(self):
        """Test that main.bicep has expected outputs"""
        bicep_file = INFRA_DIR / "main.bicep"
        content = bicep_file.read_text()
        
        assert "output aiResourceName" in content, "main.bicep should output aiResourceName"
        assert "output storageName" in content, "main.bicep should output storageName"
        assert "output acrLoginServer" in content, "main.bicep should output acrLoginServer"


class TestStorageBicep:
    """Tests specific to storage.bicep"""

    def test_storage_has_required_parameters(self):
        """Test that storage.bicep has expected parameters"""
        bicep_file = INFRA_DIR / "storage.bicep"
        content = bicep_file.read_text()
        
        assert "param location" in content, "storage.bicep should have location parameter"
        assert "param storageAccountName" in content, "storage.bicep should have storageAccountName parameter"

    def test_storage_creates_container(self):
        """Test that storage.bicep creates the bi-data container"""
        bicep_file = INFRA_DIR / "storage.bicep"
        content = bicep_file.read_text()
        
        assert "'bi-data'" in content, "storage.bicep should create bi-data container"
        assert "isHnsEnabled: true" in content, "storage.bicep should enable hierarchical namespace"

    def test_storage_creates_reports_container(self):
        """Tests that storage.bicep creates the bi-reports container"""
        bicep_file = INFRA_DIR / "storage.bicep"
        content = bicep_file.read_text()
        
        assert "'bi-reports'" in content, "storage.bicep should create bi-reports container"
        assert "isHnsEnabled: true" in content, "storage.bicep should enable hierarchical namespace"


class TestAIFoundryBicep:
    """Tests specific to ai-foundry.bicep"""

    def test_aifoundry_has_required_parameters(self):
        """Test that ai-foundry.bicep has expected parameters"""
        bicep_file = INFRA_DIR / "ai-foundry.bicep"
        content = bicep_file.read_text()
        
        assert "param location" in content, "ai-foundry.bicep should have location parameter"
        assert "param aiResourceName" in content, "ai-foundry.bicep should have aiResourceName parameter"
        assert "param projectName" in content, "ai-foundry.bicep should have projectName parameter"

    def test_aifoundry_deploys_model(self):
        """Test that ai-foundry.bicep deploys GPT model"""
        bicep_file = INFRA_DIR / "ai-foundry.bicep"
        content = bicep_file.read_text()
        
        assert "gpt-4.1-mini" in content, "ai-foundry.bicep should deploy gpt-4.1-mini model"
        assert "Microsoft.CognitiveServices/accounts/deployments" in content

    def test_aifoundry_creates_project(self):
        """Test that ai-foundry.bicep creates AI project"""
        bicep_file = INFRA_DIR / "ai-foundry.bicep"
        content = bicep_file.read_text()
        
        assert "Microsoft.CognitiveServices/accounts/projects" in content
        assert "Hitachi BI Analysis" in content, "ai-foundry.bicep should create Hitachi BI Analysis project"


class TestContainerBicep:
    """Tests specific to container.bicep"""

    def test_container_has_required_parameters(self):
        """Test that container.bicep has expected parameters"""
        bicep_file = INFRA_DIR / "container.bicep"
        content = bicep_file.read_text()
        
        assert "param location" in content, "container.bicep should have location parameter"
        assert "param acrName" in content, "container.bicep should have acrName parameter"

    def test_container_creates_acr(self):
        """Test that container.bicep creates Container Registry"""
        bicep_file = INFRA_DIR / "container.bicep"
        content = bicep_file.read_text()
        
        assert "Microsoft.ContainerRegistry/registries" in content, "container.bicep should create ACR resource"
        assert "output loginServer" in content, "container.bicep should output loginServer"

    def test_container_acr_sku(self):
        """Test that container.bicep uses Basic SKU"""
        bicep_file = INFRA_DIR / "container.bicep"
        content = bicep_file.read_text()
        
        assert "'Basic'" in content, "container.bicep should use Basic SKU for ACR"

    def test_container_admin_disabled(self):
        """Test that admin user is disabled in ACR"""
        bicep_file = INFRA_DIR / "container.bicep"
        content = bicep_file.read_text()
        
        assert "adminUserEnabled: false" in content, "container.bicep should disable admin user"


class TestBicepIntegration:
    """Integration tests for the complete infrastructure"""

    def test_all_files_exist(self):
        """Test that all expected Bicep files exist"""
        for bicep_file in BICEP_FILES:
            assert bicep_file.exists(), f"Expected Bicep file not found: {bicep_file}"

    def test_no_syntax_errors_in_all_files(self):
        """Test that all Bicep files compile without errors"""
        for bicep_file in BICEP_FILES:
            result = subprocess.run(
                ["az", "bicep", "build", "--file", str(bicep_file), "--stdout"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Compilation failed for {bicep_file}"
