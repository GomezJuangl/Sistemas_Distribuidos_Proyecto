import argparse
from Logica_Trafico.Ciudad_matriz import Ciudad_matriz
from Control_Semaforos.receptor_control_semaforos import ReceptorControlSemaforos

# ─── ESCENARIOS DE PRUEBA ─────────────────────────────────────────────────────
# Escenario A: 1 sensor de cada tipo, evento cada 10 s
# Escenario B: 2 sensores de cada tipo, evento cada 5 s
# Uso normal (sin argumento): grilla completa 4×4, intervalos originales
# ─────────────────────────────────────────────────────────────────────────────

ESCENARIOS = {
    "A": {"intersecciones": 1, "intervalo_camara": 10, "intervalo_gps": 10},
    "B": {"intersecciones": 2, "intervalo_camara": 5,  "intervalo_gps": 5},
}

parser = argparse.ArgumentParser(description="Simulación GITU")
parser.add_argument(
    "--escenario",
    choices=["A", "B"],
    default=None,
    help="Escenario de prueba: A (1 sensor, 10 s) o B (2 sensores, 5 s)",
)
args = parser.parse_args()

if args.escenario:
    cfg = ESCENARIOS[args.escenario]
    filas = 1
    columnas = cfg["intersecciones"]
    intervalo_camara = cfg["intervalo_camara"]
    intervalo_gps = cfg["intervalo_gps"]
    print(f"[MAIN] Escenario {args.escenario}: {columnas} intersección(es), "
          f"cámara={intervalo_camara}s, gps={intervalo_gps}s")
else:
    filas = 4
    columnas = 4
    intervalo_camara = 2
    intervalo_gps = 3

ciudad = Ciudad_matriz(
    filas=filas,
    columnas=columnas,
    broker_ip="127.0.0.1",
    broker_puerto=5555,
    tick_segundos=1,
    duracion_semaforo=15,
    intervalo_camara=intervalo_camara,
    intervalo_gps=intervalo_gps,
    intervalo_espira=30,
    log_intervalo=10,
    zonas_altas=[("B", 3)],
)

receptor_control = ReceptorControlSemaforos(ciudad, puerto=6003)
receptor_control.iniciar()
ciudad.Mostrar_matriz()
ciudad.iniciar_simulacion(duracion_total=None)