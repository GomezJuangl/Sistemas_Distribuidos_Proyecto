from Logica_Trafico.Ciudad_matriz import Ciudad_matriz
from Control_Semaforos.receptor_control_semaforos import ReceptorControlSemaforos
ciudad = Ciudad_matriz(
    filas=4,
    columnas=4,
    broker_ip="127.0.0.1",
    broker_puerto=5555,
    tick_segundos=1,
    duracion_semaforo=15,
    intervalo_camara=2,
    intervalo_gps=3,
    intervalo_espira=30,
    log_intervalo=10,
    zonas_altas=[("B", 3)],
)

receptor_control = ReceptorControlSemaforos(ciudad, puerto=6003)
receptor_control.iniciar()
ciudad.Mostrar_matriz()
ciudad.iniciar_simulacion(duracion_total=None)