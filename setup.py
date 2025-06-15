import os
from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='store_audit_systee',
    version='1.0.0',
    packages=find_packages(exclude=['tests*']),
    include_package_data=True,
    install_requires=requirements,
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Office/Business',
    ],
    entry_points={
        'console_scripts': [
            'store-audit=manage:main',
        ],
    },
    author='Your Name',
    author_email='your.email@example.com',
    description='A Django-based store audit system for inventory and sales management',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/store-audit-system',
    keywords='django inventory sales management',
)
