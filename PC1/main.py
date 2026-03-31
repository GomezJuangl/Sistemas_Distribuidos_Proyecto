from Ciudad_matriz import Ciudad_matriz

# Parámetros configurables: filas, columnas, IP del broker, puerto del broker
ciudad = Ciudad_matriz(filas=4, columnas=4, broker_ip="127.0.0.1", broker_puerto=5555)
ciudad.Mostrar_matriz()
