import unittest
from metadata_processing import __version__


class TestVersion(unittest.TestCase):
    def test_version(self):
        assert __version__ == '0.1.0'
