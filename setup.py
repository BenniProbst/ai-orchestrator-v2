"""Setup script for AI Orchestrator V2"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="ai-orchestrator-v2",
    version="2.0.0",
    description="Bidirektionales AI Master-Worker System mit Rollentausch",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="BenniProbst",
    url="https://github.com/BenniProbst/ai-orchestrator-v2",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "pyyaml>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "pytest-mock>=3.10",
            "mypy>=1.0",
            "black>=23.0",
            "isort>=5.12",
            "flake8>=6.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ai-orchestrator=orchestrator:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
