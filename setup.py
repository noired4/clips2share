from setuptools import setup, find_packages

setup(
    name='clips2share',
    version='0.0.1',
    url='https://codeberg.org/c2s/clips2share',
    author='c2s',
    author_email='c2s@noreply.codeberg.org',
    description='Create a torrent including metadata from a c4s link',
    long_description='Create a torrent including header image, thumbnails and all other metadata that can be extracted from a c4s link',
    packages=find_packages(),
    install_requires=[
        'beautifulsoup4',
        'requests',
        'torf',
        'vcsi'
    ],
)