import string
import time

from Logica_Trafico.Interseccion import Interseccion
from Logica_Trafico.Semaforo import Semaforo


class Ciudad_matriz:
    def __init__(self,filas,columnas,broker_ip,broker_puerto,tick_segundos=1,duracion_semaforo=15,intervalo_camara=2,intervalo_gps=3,intervalo_espira=30,log_intervalo=10,zonas_altas=None):
        self.Filas = filas
        self.Columnas = columnas
        self.Broker_ip = broker_ip
        self.Broker_puerto = broker_puerto

        self.tick_segundos = tick_segundos
        self.duracion_semaforo = duracion_semaforo
        self.intervalo_camara = intervalo_camara
        self.intervalo_gps = intervalo_gps
        self.intervalo_espira = intervalo_espira
        self.log_intervalo = log_intervalo

        self.zonas_altas = zonas_altas or []
        self.Matriz = []

        self.construir_matriz()

    def obtener_direccion_fila(self, indice_fila):
        return "IZQ_DER" if indice_fila % 2 == 0 else "DER_IZQ"

    def obtener_direccion_columna(self, indice_columna):
        return "ARR_ABJ" if indice_columna % 2 == 0 else "ABJ_ARR"

    def obtener_fase_inicial(self, indice_fila, indice_columna):
        if (indice_fila + indice_columna) % 2 == 0:
            return Semaforo.H_GREEN
        return Semaforo.V_GREEN

    def obtener_offset_inicial(self, indice_fila, indice_columna):
        # Desfase para que no cambien todos juntos
        return (indice_fila * 3 + indice_columna * 2) % self.duracion_semaforo

    def obtener_demanda(self, letra, col, indice_fila, indice_columna):
        if (letra, col) in self.zonas_altas:
            return "alta"

        es_borde = (
            indice_fila == 0
            or indice_fila == self.Filas - 1
            or indice_columna == 0
            or indice_columna == self.Columnas - 1
        )

        if es_borde:
            return "baja"
        return "media"

    def construir_matriz(self):
        letras = list(string.ascii_uppercase[: self.Filas])

        for i, letra in enumerate(letras):
            fila = []
            direccion_fila = self.obtener_direccion_fila(i)

            for j, col in enumerate(range(1, self.Columnas + 1)):
                direccion_columna = self.obtener_direccion_columna(j)
                fase_inicial = self.obtener_fase_inicial(i, j)
                offset_inicial = self.obtener_offset_inicial(i, j)
                demanda = self.obtener_demanda(letra, col, i, j)

                interseccion = Interseccion(
                    M=letra,
                    N=col,
                    broker_ip=self.Broker_ip,
                    broker_puerto=self.Broker_puerto,
                    direccion_fila=direccion_fila,
                    direccion_columna=direccion_columna,
                    demanda=demanda,
                    fase_inicial=fase_inicial,
                    offset_inicial=offset_inicial,
                    duracion_semaforo=self.duracion_semaforo,
                    tick_segundos=self.tick_segundos,
                    intervalo_camara=self.intervalo_camara,
                    intervalo_gps=self.intervalo_gps,
                    intervalo_espira=self.intervalo_espira,
                    log_intervalo=self.log_intervalo,
                )
                fila.append(interseccion)

            self.Matriz.append(fila)

    def Mostrar_matriz(self):
        print("=" * 80)
        print("📍 CIUDAD - CONFIGURACIÓN INICIAL")
        print("=" * 80)
        for fila in self.Matriz:
            for interseccion in fila:
                interseccion.Mostrar_IDS()
                print("----------")

    def iniciar_simulacion(self, duracion_total=None):
        print("\n" + "=" * 60)
        print("🚦 INICIANDO CIUDAD EN PARALELO")
        print("=" * 60)
        print(f"Tick: {self.tick_segundos}s")
        print(f"Cámara: {self.intervalo_camara}s | GPS: {self.intervalo_gps}s | Espira: {self.intervalo_espira}s")
        print("-" * 60)

        for fila in self.Matriz:
            for interseccion in fila:
                interseccion.iniciar()

        try:
            if duracion_total is None:
                while True:
                    time.sleep(1)
            else:
                time.sleep(duracion_total)

        except KeyboardInterrupt:
            print("\n⏹️  Simulación detenida por el usuario")

        finally:
            self.detener_simulacion()

    def detener_simulacion(self):
        print("\n🛑 Deteniendo intersecciones...")
        for fila in self.Matriz:
            for interseccion in fila:
                interseccion.detener()

    def obtener_interseccion(self, letra, numero):
        for fila in self.Matriz:
            for interseccion in fila:
                if interseccion.M == letra and interseccion.N == numero:
                    return interseccion
        return None