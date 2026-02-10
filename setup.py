from setuptools import setup, find_packages
setup(
    name='todotool',
    version='0.1.0',
    packages=['todotool'],
    package_dir={'todotool': '.'},
    python_requires='>=3.11',
    entry_points={'console_scripts': ['todotool=todotool.cli:main']},
    description='HurricaneSoft 待辦事項管理 CLI 工具',
)
