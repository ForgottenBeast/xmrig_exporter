import setuptools


setuptools.setup(
    name="xmrig_exporter",
    version="1.2.0",
    author="Steven Brudenell",
    author_email="steven.brudenell@gmail.com",
    packages=setuptools.find_packages(),
    install_requires=[
        "requests>=2.18.4",
        "prometheus_client>=0.2.0",
        "pyyaml>=3.12",
    ],
    entry_points={
        "console_scripts": [
            "xmrig_exporter = xmrig_exporter:exporter_main",
        ],
    },
)
