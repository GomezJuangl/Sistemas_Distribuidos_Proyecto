import zmq
import string
from Interseccion import Interseccion

class Ciudad_matriz:
    def __init__(self, filas, columnas, broker_ip, broker_puerto):
        """
        filas:         número de filas de la cuadrícula (máx. 26 por el alfabeto)
        columnas:      número de columnas de la cuadrícula
        broker_ip:     IP del broker ZMQ en PC1 (ej. "127.0.0.1")
        broker_puerto: puerto del broker ZMQ (ej. 5555)
        """
        self.Filas = filas
        self.Columnas = columnas
        self.Broker_ip = broker_ip
        self.Broker_puerto = broker_puerto
        self.Matriz = []

        # Un solo contexto y un solo socket PUB compartido por TODOS los sensores
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.connect(f"tcp://{self.Broker_ip}:{self.Broker_puerto}")

        self.construir_matriz()

    def construir_matriz(self):
        # Genera las letras de fila dinámicamente: A, B, C, ... según self.Filas
        letras = list(string.ascii_uppercase[:self.Filas])
        for letra in letras:
            fila = []
            for col in range(1, self.Columnas + 1):
                interseccion = Interseccion(letra, col, self.socket)
                fila.append(interseccion)
            self.Matriz.append(fila)

    def Mostrar_matriz(self):
        for fila in self.Matriz:
            for interseccion in fila:
                interseccion.Mostrar_IDS()
                print("----------")