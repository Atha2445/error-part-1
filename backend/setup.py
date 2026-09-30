from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# Read requirements.txt if present
req_file = here / "requirements.txt"
install_requires = []
if req_file.exists():
    install_requires = [l.strip() for l in req_file.read_text().splitlines() if l.strip() and not l.strip().startswith('#')]

setup(
    name="ids-backend",
    version="0.1.0",
    description="IDS backend for video agent",
    packages=find_packages(),
    py_modules=["main"],
    include_package_data=True,
    install_requires=install_requires + ["ids_vlm_inference>=0.1.0"],
    entry_points={
        "console_scripts": [
            "vids-agent=main:main"
        ]
    },
    python_requires=">=3.9",
)
