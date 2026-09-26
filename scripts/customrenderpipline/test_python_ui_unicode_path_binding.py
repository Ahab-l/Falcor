"""Focused source guard; runtime conversion is covered by the native CPU test."""
from pathlib import Path
import unittest


class PythonUIUnicodePathBindingTests(unittest.TestCase):
    def test_file_dialog_uses_shared_utf8_path_converter(self):
        source = (Path(__file__).parents[2] / 'Source/Falcor/Utils/UI/PythonUI.cpp').read_text(encoding='utf-8')
        self.assertIn('openFileDialog({}, path) ? pathToUtf8(path)', source)


if __name__ == '__main__':
    unittest.main()
