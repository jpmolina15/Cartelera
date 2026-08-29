"""Arma el HTML final: plantilla + datos embebidos + app.js."""
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = RAIZ / "templates"


def render(dataset, salida):
    shell = (TEMPLATES / "shell.html").read_text(encoding="utf-8")
    app = (TEMPLATES / "app.js").read_text(encoding="utf-8")
    # '</' se escapa para que un título con esa secuencia no cierre el <script>.
    payload = json.dumps(dataset, ensure_ascii=False,
                         separators=(",", ":")).replace("</", "<\\/")
    html = (shell
            + "\n<script>window.__DATA__=" + payload + ";</script>\n"
            + "<script>\n" + app + "\n</script>\n")
    pathlib.Path(salida).write_text(html, encoding="utf-8")
    return len(html)
