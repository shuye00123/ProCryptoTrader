#!/usr/bin/env python3
"""
ProCryptoTrader Setup Script

Professional cryptocurrency quantitative trading system
"""

from setuptools import setup, find_packages
import os
from pathlib import Path

# Read README file
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding='utf-8') if readme_path.exists() else ""

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_path.exists():
    with open(requirements_path, 'r', encoding='utf-8') as f:
        requirements = [
            line.strip() for line in f
            if line.strip() and not line.startswith('#') and not line.startswith('-')
        ]

# Core requirements (excluding optional ones)
core_requirements = [
    req for req in requirements
    if req and not any(keyword in req.lower() for keyword in ['pytest', 'black', 'flake8', 'mypy'])
]

setup(
    name="procrypto-trader",
    version="1.0.0",
    author="ProCryptoTrader Team",
    author_email="contact@procrypto.trader",
    description="Professional cryptocurrency quantitative trading system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/ProCryptoTrader",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=core_requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "isort>=5.12.0",
            "mypy>=1.4.0",
        ],
        "cache": [
            "redis>=4.5.0",
            "aioredis>=2.0.0",
        ],
        "web": [
            "fastapi>=0.100.0",
            "uvicorn>=0.23.0",
            "pydantic>=2.0.0",
        ],
        "async": [
            "aiohttp>=3.8.0",
            "aiofiles>=23.0.0",
        ],
        "ml": [
            "scikit-learn>=1.3.0",
            "joblib>=1.3.0",
        ],
        "security": [
            "cryptography>=41.0.0",
            "keyring>=24.0.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
        ],
        "cloud": [
            "boto3>=1.26.0",
            "oss2>=2.17.0",
        ],
        "all": [
            "redis>=4.5.0",
            "aioredis>=2.0.0",
            "fastapi>=0.100.0",
            "uvicorn>=0.23.0",
            "pydantic>=2.0.0",
            "aiohttp>=3.8.0",
            "aiofiles>=23.0.0",
            "scikit-learn>=1.3.0",
            "joblib>=1.3.0",
            "cryptography>=41.0.0",
            "keyring>=24.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "procrypto-trader=core.main:main",
            "procrypto-backtest=examples.backtest_example:main",
            "procrypto-live=examples.live_example:main",
        ],
    },
    include_package_data=True,
    package_data={
        "core": [
            "configs/*.yaml",
            "data/repositories/*",
        ],
    },
    zip_safe=False,
)