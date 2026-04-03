from Ciudad_matriz import Ciudad_matriz

ciudad = Ciudad_matriz(
    filas=2,
    columnas=2,
    broker_ip="127.0.0.1",
    broker_puerto=5555,
    tick_segundos=1,
    duracion_semaforo=20,
    intervalo_camara=10,
    intervalo_gps=15,
    intervalo_espira=30,
    log_intervalo=10,
    zonas_altas=[("B", 3)],
)

ciudad.Mostrar_matriz()
ciudad.iniciar_simulacion(duracion_total=None)