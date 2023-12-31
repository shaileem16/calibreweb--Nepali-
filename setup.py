
#  """Calibre-web-nepali distribution package setuptools installer."""

from setuptools import setup
from setuptools import find_packages
import os
import re
import codecs

here = os.path.abspath(os.path.dirname(__file__))

def read(*parts):
    with codecs.open(os.path.join(here, *parts), 'r') as fp:
        return fp.read()

def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^STABLE_VERSION\s+=\s+{['\"]version['\"]:\s*['\"](.*)['\"]}",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")

setup(
    packages=find_packages("src"),
    package_dir = {'': 'src'},
    version=find_version( "/home/shail/calibreweb--Nepali-/cps/constants.py")
)