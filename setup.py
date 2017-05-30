from setuptools import setup

setup(
    name='Flask-Mailgun',
    version='1.5',
    description='Mailgun integration for Flask',
    py_modules=['flask_mailgun'],
    install_requires=[
        'Flask>=0.11',
        'html2text>=2016',
        'requests>=2.12',
    ])
