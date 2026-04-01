from setuptools import setup, find_packages

setup(
    name='steady',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'numpy',
        'evdev',
        'pystray',
        'Pillow',
    ],
    extras_require={
        'dev': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            'steady-tray = steady.app:main',
        ],
    },
    author='Your Name',
    author_email='your.email@example.com',
    description='Tremor Assistance Accessibility Tool',
    long_description='An adaptive tremor filtering application',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Healthcare Industry',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10'
    ],
)
