"""
Prueba de estrés — Carga máxima del sistema GITU.

Fija el broker en 8 hilos y sube la tasa del generador progresivamente.
Para cada tasa mide durante VENTANA_SEG segundos:
  1. Throughput real (registros nuevos en BD réplica)
  2. CPU de analítica (psutil, local en PC2)
  3. Tasa de pérdida = 1 - (registros_reales / mensajes_enviados)

Al final genera:
  - PC2/Pruebas/estres_resultados.csv  (resumen por tasa)
  - PC2/Pruebas/graficas/estres_carga_maxima.png

Uso (en PC2, con el sistema ya levantado):
    python3 prueba_estres_cpu.py
    python3 prueba_estres_cpu.py --tasas 100,500,1000,2000,5000
    python3 prueba_estres_cpu.py --ventana 90 --tasas 50,100,200,500,1000,2000

IMPORTANTE: El generador corre en PC1. Este script le indica a PC1 qué tasa
usar mediante un socket ZMQ REQ/REP (puerto 6010). En PC1 debe estar corriendo
el generador_carga_estres.py que escucha en ese puerto.

Orden de ejecución:
  1. PC3: ./pc3_servicios.sh
  2. PC1: ./pc1_estres.sh
  3. PC2: ./pc2_estres.sh   (este script corre dentro de pc2_estres.sh)
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

try:
    import psutil
except ImportError:
    print("[ERROR] psutil no encontrado. Instalar: pip install psutil")
    sys.exit(1)

import zmq

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
PC1_IP = "10.43.99.110"
GENERADOR_CONTROL_PUERTO = 6010  # REQ/REP para controlar el generador en PC1

DB_REPLICA_PATH = os.path.join(os.path.dirname(__file__), "..", "BaseDatosReplica", "bd_replica.db")
RESULTADOS_CSV = os.path.join(os.path.dirname(__file__), "estres_resultados.csv")
GRAFICAS_DIR = os.path.join(os.path.dirname(__file__), "graficas")

VENTANA_SEG = 60       # duración de medición por cada tasa
PAUSA_ENTRE = 10       # pausa entre tasas para estabilizar
CPU_INTERVALO = 1      # intervalo de muestreo CPU en segundos
TASAS_DEFAULT = [50, 100, 200, 500, 1000, 2000, 5000]
# ──────────────────────────────────────────────────────────────────────────────


def encontrar_pid_analitica() -> int:
    """Busca el PID del proceso servicio_analitica.py."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline)
            if "servicio_analitica.py" in cmd_str:
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return -1


def contar_registros_bd() -> int:
    """Cuenta TODOS los registros en BD réplica."""
    db_path = os.path.abspath(DB_REPLICA_PATH)
    if not os.path.exists(db_path):
        return 0
    con = sqlite3.connect(db_path)
    total = 0
    try:
        for tabla in ("GPS", "CAMARA", "ESPIRA", "DECISIONES"):
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                total += n
            except sqlite3.OperationalError:
                pass
    finally:
        con.close()
    return total


def enviar_comando_generador(ctx, comando: dict, pc1_ip: str = PC1_IP, timeout_ms=10000) -> dict:
    """Envía un comando al generador en PC1 y espera respuesta."""
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    sock.setsockopt(zmq.LINGER, 1000)
    sock.connect(f"tcp://{pc1_ip}:{GENERADOR_CONTROL_PUERTO}")
    try:
        sock.send_string(json.dumps(comando))
        resp = sock.recv_string()
        return json.loads(resp)
    except zmq.Again:
        print(f"    [ERROR] Sin respuesta del generador en PC1 (timeout)")
        return {"status": "error", "msg": "timeout"}
    finally:
        sock.close()


def medir_cpu_durante(pid: int, duracion: int, intervalo: float = 1.0) -> list:
    """Muestrea el CPU% de un proceso durante `duracion` segundos."""
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return []

    muestras = []
    proc.cpu_percent()  # descarta primera lectura (siempre 0)
    t_fin = time.monotonic() + duracion
    while time.monotonic() < t_fin:
        time.sleep(intervalo)
        try:
            cpu = proc.cpu_percent()
            muestras.append(cpu)
        except psutil.NoSuchProcess:
            break
    return muestras


def ejecutar_prueba_tasa(ctx, tasa: int, ventana: int, pid_analitica: int, pc1_ip: str) -> dict:
    """Ejecuta una ronda de prueba para una tasa dada."""
    print(f"\n{'─'*60}")
    print(f"  TASA: {tasa} msg/s | Ventana: {ventana}s")
    print(f"{'─'*60}")

    # Decirle al generador que empiece con esta tasa
    print(f"    Iniciando generador a {tasa} msg/s...")
    resp = enviar_comando_generador(ctx, {
        "accion": "iniciar",
        "tasa": tasa,
        "duracion": ventana + 10  # un poco más para cubrir la ventana completa
    }, pc1_ip=pc1_ip)
    if resp.get("status") != "ok":
        print(f"    [ERROR] Generador respondió: {resp}")
        return None

    # Esperar 5s para que el generador arranque y el pipeline se estabilice
    time.sleep(5)

    # Contar registros DESPUÉS de estabilizar (así no contamos la ráfaga inicial)
    registros_antes = contar_registros_bd()

    # Medir CPU de analítica durante la ventana
    print(f"    Midiendo CPU de analítica durante {ventana}s...")
    muestras_cpu = medir_cpu_durante(pid_analitica, ventana, CPU_INTERVALO)

    # Pausa para que analítica drene lo que le quede en buffer
    time.sleep(3)

    # Contar registros después
    registros_despues = contar_registros_bd()
    registros_nuevos = registros_despues - registros_antes

    # Pedir al generador cuántos mensajes envió realmente
    resp_stats = enviar_comando_generador(ctx, {"accion": "stats"}, pc1_ip=pc1_ip)
    # Usamos tasa * ventana como estimación de msgs durante la ventana de medición
    # (el generador reporta el total incluyendo warmup, que no medimos)
    msgs_enviados = tasa * ventana

    # Calcular métricas
    cpu_promedio = sum(muestras_cpu) / len(muestras_cpu) if muestras_cpu else 0
    cpu_max = max(muestras_cpu) if muestras_cpu else 0
    throughput_real = registros_nuevos / ventana if ventana > 0 else 0
    tasa_perdida = 1 - (registros_nuevos / msgs_enviados) if msgs_enviados > 0 else 0
    tasa_perdida = max(0, min(1, tasa_perdida))  # clamp 0-1

    resultado = {
        "tasa_inyeccion": tasa,
        "msgs_enviados": msgs_enviados,
        "registros_bd": registros_nuevos,
        "throughput_real_msg_s": round(throughput_real, 1),
        "tasa_perdida_pct": round(tasa_perdida * 100, 1),
        "cpu_analitica_prom": round(cpu_promedio, 1),
        "cpu_analitica_max": round(cpu_max, 1),
        "muestras_cpu": len(muestras_cpu),
    }

    print(f"    Enviados:       {msgs_enviados}")
    print(f"    En BD:          {registros_nuevos}")
    print(f"    Throughput real: {throughput_real:.1f} msg/s")
    print(f"    Pérdida:        {tasa_perdida*100:.1f}%")
    print(f"    CPU analítica:  prom={cpu_promedio:.1f}% max={cpu_max:.1f}%")

    return resultado


def guardar_resultados(resultados: list):
    """Guarda el CSV con los resultados."""
    with open(RESULTADOS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "tasa_inyeccion", "msgs_enviados", "registros_bd",
            "throughput_real_msg_s", "tasa_perdida_pct",
            "cpu_analitica_prom", "cpu_analitica_max", "muestras_cpu"
        ])
        w.writeheader()
        for r in resultados:
            w.writerow(r)
    print(f"\n[OK] Resultados guardados en {RESULTADOS_CSV}")


def generar_grafica(resultados: list):
    """Genera la gráfica de carga máxima."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        print("[WARN] matplotlib no disponible, skip gráfica")
        return

    os.makedirs(GRAFICAS_DIR, exist_ok=True)

    tasas = [r["tasa_inyeccion"] for r in resultados]
    perdida = [r["tasa_perdida_pct"] for r in resultados]
    throughput = [r["throughput_real_msg_s"] for r in resultados]

    fig, ax1 = plt.subplots(figsize=(11, 6))

    color_tp = "#4C72B0"
    color_loss = "#C44E52"

    # ─── Throughput (eje izquierdo) ───
    ln1 = ax1.plot(tasas, throughput, "o-", color=color_tp, linewidth=2.5,
                   markersize=10, label="Throughput real (msg/s)", zorder=3)
    ax1.set_ylabel("Throughput real (msg/s)", color=color_tp, fontsize=12, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor=color_tp, labelsize=10)
    ax1.set_xlabel("Tasa de inyección (msg/s)", fontsize=12, fontweight="bold")
    ax1.set_xscale("log")
    ax1.set_xticks(tasas)
    ax1.get_xaxis().set_major_formatter(ticker.ScalarFormatter())
    ax1.tick_params(axis="x", labelsize=10)
    ax1.grid(axis="y", linestyle="--", alpha=0.3)
    ax1.grid(axis="x", linestyle="--", alpha=0.15)

    # Etiquetas throughput
    for i, (x, y) in enumerate(zip(tasas, throughput)):
        ax1.annotate(f"{y:.0f}", (x, y), textcoords="offset points",
                     xytext=(0, 10), ha="center", fontsize=9, fontweight="bold",
                     color=color_tp)

    # ─── Tasa de pérdida (eje derecho) ───
    ax1b = ax1.twinx()
    ln2 = ax1b.plot(tasas, perdida, "s--", color=color_loss, linewidth=2,
                    markersize=9, label="Tasa de pérdida (%)", zorder=3)
    ax1b.set_ylabel("Tasa de pérdida (%)", color=color_loss, fontsize=12, fontweight="bold")
    ax1b.tick_params(axis="y", labelcolor=color_loss, labelsize=10)
    ax1b.set_ylim(-5, 105)

    # Etiquetas pérdida
    for x, y in zip(tasas, perdida):
        ax1b.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                      xytext=(12, -5), ha="left", fontsize=9, fontweight="bold",
                      color=color_loss)

    # ─── Zona de saturación ───
    # Encontrar el punto donde pérdida > 10%
    sat_idx = None
    for i, p in enumerate(perdida):
        if p > 10:
            sat_idx = i
            break

    if sat_idx is not None and sat_idx > 0:
        # Línea divisoria entre la última tasa sin pérdida y la primera con pérdida
        sat_x = (tasas[sat_idx - 1] * tasas[sat_idx]) ** 0.5  # media geométrica (log scale)
        ax1.axvline(x=sat_x, color="#E8A838", linestyle=":", linewidth=2, alpha=0.8)
        ax1.axvspan(sat_x, max(tasas) * 1.5, alpha=0.06, color="#C44E52")
        ax1.axvspan(min(tasas) * 0.7, sat_x, alpha=0.06, color="#55A868")

        # Etiquetas de zona
        zona_ok_x = (min(tasas) * tasas[sat_idx - 1]) ** 0.5
        zona_sat_x = (tasas[sat_idx] * max(tasas)) ** 0.5
        y_top = max(throughput) + (max(throughput) - min(throughput)) * 0.25
        ax1.text(zona_ok_x, y_top, "Sistema\nabsorbe todo",
                 ha="center", fontsize=9, color="#55A868", fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#d4edda",
                           edgecolor="#55A868", alpha=0.8))
        ax1.text(zona_sat_x, y_top, "Zona de saturación\n(mensajes se pierden)",
                 ha="center", fontsize=9, color="#C44E52", fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#f8d7da",
                           edgecolor="#C44E52", alpha=0.8))

    # ─── Anotación del pico de throughput ───
    pico_idx = throughput.index(max(throughput))
    ax1.annotate(f"Pico: {max(throughput):.0f} msg/s\n(a {int(tasas[pico_idx])} msg/s inyectados)",
                 xy=(tasas[pico_idx], max(throughput)),
                 xytext=(60, -40), textcoords="offset points",
                 fontsize=10, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color="#333", lw=1.5),
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff3cd",
                           edgecolor="#ffc107", alpha=0.95))

    # ─── Anotación capacidad máxima sostenida (última tasa con 0% pérdida) ───
    ultima_ok = 0
    for i, p in enumerate(perdida):
        if p == 0:
            ultima_ok = i
    ax1.annotate(f"Capacidad máxima sostenida:\n~{throughput[ultima_ok]:.0f} msg/s (0% pérdida)",
                 xy=(tasas[ultima_ok], throughput[ultima_ok]),
                 xytext=(-20, -50), textcoords="offset points",
                 fontsize=10, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color="#333", lw=1.5),
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="#d4edda",
                           edgecolor="#28a745", alpha=0.95))

    # ─── Leyenda combinada ───
    lines = ln1 + ln2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="center right", fontsize=10,
               framealpha=0.9, edgecolor="#ccc")

    ax1.set_title("Prueba de Estrés — Carga Máxima del Sistema GITU\n"
                  "(Broker 8 hilos, Escenario A, ventana 60s)",
                  fontsize=14, fontweight="bold", pad=15)
    ax1.spines[["top"]].set_visible(False)
    ax1b.spines[["top"]].set_visible(False)

    fig.tight_layout()
    ruta = os.path.join(GRAFICAS_DIR, "estres_carga_maxima.png")
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Gráfica guardada en {ruta}")


def main():
    parser = argparse.ArgumentParser(description="Prueba de estrés — carga máxima GITU")
    parser.add_argument("--tasas", default=",".join(str(t) for t in TASAS_DEFAULT),
                        help="Tasas a probar, separadas por coma (default: 50,100,200,500,1000,2000,5000)")
    parser.add_argument("--ventana", type=int, default=VENTANA_SEG,
                        help=f"Duración de medición por tasa en segundos (default: {VENTANA_SEG})")
    parser.add_argument("--pc1-ip", default=PC1_IP,
                        help=f"IP de PC1 (default: {PC1_IP})")
    args = parser.parse_args()

    pc1_ip = args.pc1_ip

    tasas = [int(t.strip()) for t in args.tasas.split(",")]
    tasas.sort()

    # Encontrar PID de analítica
    pid_analitica = encontrar_pid_analitica()
    if pid_analitica < 0:
        print("[ERROR] No se encontró el proceso servicio_analitica.py corriendo.")
        print("        Levanta el sistema antes de correr esta prueba.")
        sys.exit(1)
    print(f"[OK] Analítica encontrada: PID {pid_analitica}")

    ctx = zmq.Context()

    print(f"\n{'='*60}")
    print(f"  PRUEBA DE ESTRÉS — CARGA MÁXIMA")
    print(f"  Tasas a probar: {tasas} msg/s")
    print(f"  Ventana por tasa: {args.ventana}s")
    print(f"  Tiempo estimado: ~{len(tasas) * (args.ventana + PAUSA_ENTRE) // 60 + 1} min")
    print(f"{'='*60}")

    resultados = []
    for i, tasa in enumerate(tasas):
        resultado = ejecutar_prueba_tasa(ctx, tasa, args.ventana, pid_analitica, pc1_ip)
        if resultado:
            resultados.append(resultado)

        # Pausa entre tasas (excepto la última)
        if i < len(tasas) - 1:
            print(f"\n    Pausa {PAUSA_ENTRE}s para estabilizar...")
            # Decirle al generador que pare
            enviar_comando_generador(ctx, {"accion": "parar"}, pc1_ip=pc1_ip)
            time.sleep(PAUSA_ENTRE)

    # Parar generador al final
    enviar_comando_generador(ctx, {"accion": "parar"}, pc1_ip=pc1_ip)

    ctx.term()

    if resultados:
        guardar_resultados(resultados)
        generar_grafica(resultados)

        # Resumen final
        print(f"\n{'='*60}")
        print(f"  RESUMEN")
        print(f"{'='*60}")
        max_tp = max(resultados, key=lambda r: r["throughput_real_msg_s"])
        print(f"  Throughput máximo: {max_tp['throughput_real_msg_s']} msg/s "
              f"(a tasa {max_tp['tasa_inyeccion']} msg/s)")

        # Encontrar punto de saturación
        for r in resultados:
            if r["tasa_perdida_pct"] > 10:
                print(f"  Punto de saturación: {r['tasa_inyeccion']} msg/s "
                      f"(pérdida {r['tasa_perdida_pct']}%)")
                break
        else:
            print(f"  El sistema NO se saturó con las tasas probadas.")
            print(f"  Intentar con tasas más altas.")

        max_cpu = max(resultados, key=lambda r: r["cpu_analitica_prom"])
        print(f"  CPU analítica máximo: {max_cpu['cpu_analitica_prom']}% "
              f"(a tasa {max_cpu['tasa_inyeccion']} msg/s)")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
