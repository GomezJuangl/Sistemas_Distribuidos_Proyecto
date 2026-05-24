"""
Mide VD1 (registros en BD réplica) y VD2 (latencia comando→semáforo).

Uso:
    python3 medir_rendimiento.py --escenario A --diseno original
    python3 medir_rendimiento.py --escenario A --diseno multihilo_4
    python3 medir_rendimiento.py --escenario A --diseno multihilo_4 --con-generador
    python3 medir_rendimiento.py --escenario A --diseno multihilo_4 --con-generador --tasa-generador 2000
    python3 medir_rendimiento.py --escenario A --diseno multihilo_4 --red congestionada

--diseno acepta "original" o "multihilo_N" donde N es un entero >= 1.
--con-generador lanza PC1/generador_carga.py como subprocess durante VD1 (solo localhost).
--red etiqueta el entorno de red en el CSV (limpia | congestionada).

Repeticiones:
    - VD2: 30 mediciones consecutivas (tarda ~1 min en total)
    - VD1: 3 ventanas de 2 min consecutivas (tarda ~6 min en total)
    El sistema debe estar levantado y estable antes de correr este script.

Archivos generados:
    - PC2/Pruebas/detalle_<escenario>_<diseno>.csv  — todas las mediciones individuales
    - PC2/Pruebas/resultados.csv                    — promedio de cada caso (fila nueva por caso)
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import zmq
from datetime import datetime
from statistics import mean, median, stdev


def _tipo_diseno(valor: str) -> str:
    """Tipo argparse: acepta 'original' o 'multihilo_N' con N entero >= 1."""
    if valor in ("original", "multihilo"):
        return valor
    m = re.fullmatch(r"multihilo_(\d+)", valor)
    if m and int(m.group(1)) >= 1:
        return valor
    raise argparse.ArgumentTypeError(
        f"'{valor}' no es válido. Use 'original' o 'multihilo_N' con N entero >= 1."
    )


# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
DB_REPLICA_PATH  = os.path.join(os.path.dirname(__file__), "..", "BaseDatosReplica", "bd_replica.db")
VD2_LOG          = os.path.join(os.path.dirname(__file__), "vd2_fin.log")
RESULTADOS_CSV   = os.path.join(os.path.dirname(__file__), "resultados.csv")

# t0 se captura en PC3 (disparador_vd2.py) para incluir el hop PC3→PC2 en la latencia.
PC3_IP               = "10.43.100.49"
PC3_DISPARADOR_PUERTO = 6004

VD2_REPETICIONES        = 30
VD2_PAUSA_ENTRE_SEG     = 2    # pausa entre cada tiro de VD2
VD1_REPETICIONES        = 3
VD1_VENTANA_SEG         = 120  # 2 minutos por ventana
# ──────────────────────────────────────────────────────────────────────────────


def normalizar_diseno(diseno: str) -> str:
    if diseno == "multihilo":
        return "multihilo_4"
    return diseno


def enviar_comando_vd2_una_vez() -> float:
    """Envía un comando de prioridad vía el disparador en PC3 y retorna la latencia en ms (-1 si falla).

    t0 se captura en PC3 (disparador_vd2.py) justo antes de enviar el REQ a analítica,
    reproduciendo el momento exacto en que el usuario de Monitoreo manda la solicitud.
    """
    open(VD2_LOG, "w").close()

    ctx  = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, 10000)  # 10 s: incluye el round-trip PC3→analítica→PC3
    sock.connect(f"tcp://{PC3_IP}:{PC3_DISPARADOR_PUERTO}")

    params = json.dumps({"tipo": "prioridad", "interseccion": "INT_A1", "eje": "H", "duracion": 15})

    try:
        sock.send_string(params)
        respuesta_raw = sock.recv_string()
    except zmq.Again:
        print("    [VD2] Sin respuesta del disparador PC3 (timeout)")
        sock.close(); ctx.term()
        return -1.0
    finally:
        sock.close(); ctx.term()

    try:
        respuesta = json.loads(respuesta_raw)
        ts_inicio = respuesta["ts_inicio"]
    except (json.JSONDecodeError, KeyError):
        print(f"    [VD2] Respuesta inesperada del disparador: {respuesta_raw[:80]}")
        return -1.0

    time.sleep(1.0)

    ts_fin = None
    if os.path.exists(VD2_LOG):
        with open(VD2_LOG) as f:
            for line in reversed(f.readlines()):
                if "[VD2-FIN]" in line:
                    candidato = line.split("]")[1].strip().split(" ")[0]
                    if candidato >= ts_inicio:
                        ts_fin = candidato
                        break

    if not ts_fin:
        return -1.0

    fmt = "%Y-%m-%dT%H:%M:%S.%f"
    t0  = datetime.strptime(ts_inicio, fmt)
    t1  = datetime.strptime(ts_fin,    fmt)
    # t0 capturado en PC3 (disparador_vd2.py), t1 capturado en PC1 (receptor_control_semaforos.py).
    # En despliegue real, PC1 y PC3 deben estar sincronizados con NTP antes de correr este experimento;
    # sin sincronización el skew típico (10-50 ms) domina la señal medida (~2 ms) e invalida el resultado.
    return round((t1 - t0).total_seconds() * 1000, 1)


def medir_vd2_repeticiones() -> list[float]:
    print(f"\n[VD2] {VD2_REPETICIONES} mediciones (pausa {VD2_PAUSA_ENTRE_SEG}s entre cada una)...")
    resultados = []
    for i in range(1, VD2_REPETICIONES + 1):
        latencia = enviar_comando_vd2_una_vez()
        estado   = f"{latencia} ms" if latencia >= 0 else "ERROR"
        print(f"    Rep {i:02d}/{VD2_REPETICIONES}: {estado}")
        resultados.append(latencia)
        if i < VD2_REPETICIONES:
            time.sleep(VD2_PAUSA_ENTRE_SEG)
    return resultados


def contar_registros_bd(inicio: datetime, fin: datetime) -> int:
    db_path = os.path.abspath(DB_REPLICA_PATH)
    if not os.path.exists(db_path):
        print(f"    [ERROR] BD réplica no encontrada: {db_path}")
        return -1

    ts_i = inicio.isoformat(timespec="seconds")
    ts_f = fin.isoformat(timespec="seconds")
    con  = sqlite3.connect(db_path)
    total = 0
    try:
        for tabla, col in [("GPS","TIMESTAMP"), ("CAMARA","TIMESTAMP"),
                           ("ESPIRA","TIMESTAMP_FIN"), ("DECISIONES","TIMESTAMP")]:
            try:
                n = con.execute(
                    f"SELECT COUNT(*) FROM {tabla} WHERE {col} BETWEEN ? AND ?",
                    (ts_i, ts_f)
                ).fetchone()[0]
                total += n
            except sqlite3.OperationalError:
                pass
    finally:
        con.close()
    return total


def medir_vd1_repeticiones() -> list[int]:
    print(f"\n[VD1] {VD1_REPETICIONES} ventanas de {VD1_VENTANA_SEG}s...")
    resultados = []
    for i in range(1, VD1_REPETICIONES + 1):
        print(f"    Ventana {i}/{VD1_REPETICIONES} — midiendo {VD1_VENTANA_SEG}s...", end="", flush=True)
        inicio = datetime.now()
        time.sleep(VD1_VENTANA_SEG)
        fin    = datetime.now()
        count  = contar_registros_bd(inicio, fin)
        print(f" {count} registros")
        resultados.append(count)
    return resultados


def guardar_detalle(escenario: str, diseno: str, vd2_lista: list[float], vd1_lista: list[int]):
    path = os.path.join(os.path.dirname(__file__), f"detalle_{escenario}_{diseno}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tipo", "repeticion", "valor"])
        for i, v in enumerate(vd2_lista, 1):
            w.writerow(["vd2_ms", i, v])
        for i, v in enumerate(vd1_lista, 1):
            w.writerow(["vd1_registros", i, v])
    print(f"\n[OK] Detalle guardado en {path}")


def percentil(datos: list, p: float) -> float:
    s = sorted(datos)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (idx - lo), 2)


def guardar_resumen(escenario: str, diseno: str, vd2_lista: list[float], vd1_lista: list[int], red: str = "limpia"):
    vd2_validos  = [v for v in vd2_lista if v >= 0]
    vd2_mediana  = round(median(vd2_validos), 2) if vd2_validos else -1
    vd2_p90      = percentil(vd2_validos, 90) if vd2_validos else -1
    vd2_p95      = percentil(vd2_validos, 95) if vd2_validos else -1
    # Descartar ventanas VD1 con 0 registros (indican que analítica/generador
    # dejó de funcionar durante esa ventana — dato inválido, no real).
    vd1_validos  = [v for v in vd1_lista if v > 0]
    vd1_mediana  = round(median(vd1_validos), 1) if vd1_validos else -1
    vd1_prom     = round(mean(vd1_validos), 1) if vd1_validos else -1
    vd1_std      = round(stdev(vd1_validos), 2) if len(vd1_validos) > 1 else 0

    escribir_cabecera = not os.path.exists(RESULTADOS_CSV)
    with open(RESULTADOS_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if escribir_cabecera:
            w.writerow(["escenario", "diseno",
                        "vd1_mediana_registros_2min", "vd1_prom_registros_2min", "vd1_std",
                        "vd2_mediana_ms", "vd2_p90_ms", "vd2_p95_ms",
                        "vd1_repeticiones", "vd2_repeticiones", "red"])
        w.writerow([escenario, diseno, vd1_mediana, vd1_prom, vd1_std,
                    vd2_mediana, vd2_p90, vd2_p95,
                    len(vd1_validos), len(vd2_validos), red])
    print(f"[OK] Resumen guardado en {RESULTADOS_CSV}")
    return vd1_mediana, vd1_prom, vd1_std, vd2_mediana, vd2_p90, vd2_p95


def main():
    parser = argparse.ArgumentParser(description="Mide VD1 y VD2 del sistema GITU")
    parser.add_argument("--escenario", choices=["A", "B"], required=True)
    parser.add_argument("--diseno",    type=_tipo_diseno, required=True,
                        metavar="DISENO",
                        help="'original' o 'multihilo_N' con N entero >= 1")
    parser.add_argument("--solo-vd2", action="store_true",
                        help="Solo medir VD2 (skip VD1). Útil para ronda con iperf3.")
    parser.add_argument("--red", choices=["limpia", "congestionada"], default="limpia",
                        help="Etiqueta de estado de la red (para gráfica comparativa iperf3)")
    args = parser.parse_args()

    diseno = normalizar_diseno(args.diseno)

    if args.solo_vd2:
        print(f"\n{'='*60}")
        print(f"  MEDICIÓN (SOLO VD2) — Escenario {args.escenario} | Diseño: {diseno}")
        print(f"  VD2: {VD2_REPETICIONES} rep  |  Red: {args.red}")
        print(f"  Tiempo estimado: ~2 min")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print(f"  MEDICIÓN — Escenario {args.escenario} | Diseño: {diseno}")
        print(f"  VD2: {VD2_REPETICIONES} rep  |  VD1: {VD1_REPETICIONES} × {VD1_VENTANA_SEG}s")
        print(f"  Tiempo estimado: ~{(VD1_REPETICIONES * VD1_VENTANA_SEG + VD2_REPETICIONES * VD2_PAUSA_ENTRE_SEG) // 60 + 1} min")
        print(f"{'='*60}")

    vd2_lista = medir_vd2_repeticiones()

    if args.solo_vd2:
        vd1_lista = []
    else:
        vd1_lista = medir_vd1_repeticiones()

    guardar_detalle(args.escenario, diseno, vd2_lista, vd1_lista)
    vd1_mediana, vd1_prom, vd1_std, vd2_mediana, vd2_p90, vd2_p95 = guardar_resumen(
        args.escenario, diseno, vd2_lista, vd1_lista, red=args.red
    )

    vd2_validos = [v for v in vd2_lista if v >= 0]
    print(f"\n{'='*60}")
    print(f"  RESULTADOS")
    print(f"{'='*60}")
    print(f"  VD2 — latencia comando→semáforo ({len(vd2_validos)} mediciones)")
    print(f"    Mediana  : {vd2_mediana} ms  ← valor representativo")
    print(f"    P90      : {vd2_p90} ms  (90% de mediciones por debajo)")
    print(f"    P95      : {vd2_p95} ms  (95% de mediciones por debajo)")
    print(f"    Mín/Máx  : {min(vd2_validos)}/{max(vd2_validos)} ms")
    if not args.solo_vd2:
        vd1_validos = [v for v in vd1_lista if v > 0]
        print(f"  VD1 — registros en BD réplica por ventana de 2 min ({len(vd1_validos)} ventanas)")
        print(f"    Mediana  : {vd1_mediana}  ← valor representativo")
        print(f"    Promedio : {vd1_prom}  (referencia)")
        print(f"    Desv.std : {vd1_std}")
        print(f"    Mín/Máx  : {min(vd1_validos)}/{max(vd1_validos)}")
    if args.red == "congestionada":
        print(f"  Red: CONGESTIONADA (iperf3 activo)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
