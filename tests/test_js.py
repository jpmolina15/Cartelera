"""Corre las pruebas JS del bloque puro de app.js si hay Node; si no, se saltea."""
import pathlib
import shutil
import subprocess
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("node"), "node no está instalado")
class TestJS(unittest.TestCase):
    def test_node_test(self):
        archivos = sorted(str(p) for p in (RAIZ / "tests" / "js").glob("*.test.js"))
        r = subprocess.run(["node", "--test", *archivos], cwd=RAIZ,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
