#!/usr/bin/env bash
# Prueba real de TMDb en TU terminal. El token no se escribe en ningún archivo del repo.
#
#   export TMDB_TOKEN='...'      # API Read Access Token (v4), una vez por terminal
#   scripts/probar_tmdb.sh
#
# Si no está exportado, lo pide sin mostrarlo (no queda en el historial de la shell).
# Hace: corrida real -> % con tmdb_id, lista sin match, 5 enlaces de Letterboxd para
# probar a mano, y el grep anti-fuga del token en HTML, JSON, caché y log.
# No usa `env`, `printenv`, `set -x` ni imprime la variable.
set -u
cd "$(dirname "$0")/.."

if [ -z "${TMDB_TOKEN:-}" ]; then
  printf 'TMDB_TOKEN (no se muestra): ' >&2
  IFS= read -rs TMDB_TOKEN; echo >&2
fi
[ -n "$TMDB_TOKEN" ] || { echo "Sin token, nada que probar." >&2; exit 2; }
export TMDB_TOKEN

HTML=salida/cartelera-caba.html; JSON=salida/datos-caba.json; LOG=salida/prueba-tmdb.log
CACHE=data/tmdb-cache.json
mkdir -p salida
python3 run.py --salida "$HTML" --json "$JSON" >"$LOG" 2>&1
RC=$?
grep -E 'ATENCION|tmdb_id=|^dias=|sin_tmdb_id=' "$LOG"
[ $RC -eq 0 ] || { echo "run.py terminó con error ($RC); mirá $LOG"; }

python3 - "$JSON" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
fs = list(d["films"].values())
con = [f for f in fs if f.get("tmdb_id")]
print(f"\ntmdb_id: {len(con)}/{len(fs)} ({100*len(con)//max(len(fs),1)}%)  [objetivo >= 25/35]")
print("Sin match (revisar a mano; LA CASA, LA ODISEA, LOS OTROS, CARS y eventos primero):")
for f in fs:
    if not f.get("tmdb_id"):
        print("  -", f["titulo"])
print("\nPelículas con id y cómo se verificaron (revisar que los títulos tengan sentido):")
for f in con:
    print(f"  {f['titulo']}  ->  {f['titulo_en']} ({f['anio_tmdb']})  id={f['tmdb_id']}  verif={f['verif']}  score={f['score']}")
print("\n5 enlaces para probar a mano:")
for f in con[:5]:
    print(f"  https://letterboxd.com/tmdb/{f['tmdb_id']}/   <- {f['titulo']}")
PY

echo; echo "Anti-fuga (tiene que decir 0 en los cuatro):"
FALLA=0
for a in "$HTML" "$JSON" "$CACHE" "$LOG"; do
  if [ -f "$a" ]; then
    n=$(grep -c -F -f <(printf '%s\n' "$TMDB_TOKEN") "$a" 2>/dev/null); n=${n:-0}
  else n=0; fi
  echo "  $a: $n"
  [ "$n" -eq 0 ] || FALLA=1
done
[ $FALLA -eq 0 ] && echo "OK: el token no aparece." || echo "FUGA: el token aparece. No commitear ni publicar."
echo; echo "La caché ($CACHE) puede commitearse (no tiene datos sensibles); revisá 'git diff $CACHE'."
exit $FALLA
