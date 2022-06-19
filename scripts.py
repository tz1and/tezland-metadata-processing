import logging
import unittest
import colour_runner.runner

def test():
    """
    Run all unittests.
    """
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir='./tests', pattern='test_*.py')

    logging.disable(logging.CRITICAL)

    runner = colour_runner.runner.ColourTextTestRunner(verbosity=2)
    runner.run(suite)
