import random
import time
import threading
from datetime import datetime, timezone

import zmq

from GPS import GPS
from Camara import Camara
from Espira_inductiva import Espira_inductiva
from Semaforo import Semaforo


class Interseccion:
    def __init__(self,M,N,broker_ip,broker_puerto,direccion_fila,direccion_columna,demanda="media",fase_inicial="H_GREEN",offset_inicial=0,duracion_semaforo=15,tick_segundos=1,intervalo_camara=2,intervalo_gps=3,intervalo_espira=30,log_intervalo=10,):
        self.M = M
        self.N = N
        self.Interseccion = [M, N]

        self.direccion_fila = direccion_fila
        self.direccion_columna = direccion_columna
        self.demanda = demanda

        self.tick_segundos = tick_segundos
        self.intervalo_camara = intervalo_camara
        self.intervalo_gps = intervalo_gps
        self.intervalo_espira = intervalo_espira
        self.log_intervalo = log_intervalo

        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        # Estado persistente del tráfico
        if self.demanda == "baja":
            self.cola_horizontal = random.randint(0, 2)
            self.cola_vertical = random.randint(0, 2)
        elif self.demanda == "media":
            self.cola_horizontal = random.randint(1, 4)
            self.cola_vertical = random.randint(1, 4)
        else:  # alta
            self.cola_horizontal = random.randint(3, 6)
            self.cola_vertical = random.randint(3, 6)

        self.velocidad_promedio = 40
        self.nivel_congestion = "BAJA"
        self.estado_trafico = "NORMAL"

        self.vehiculos_espira_acumulados = 0
        self.ventana_espira_inicio = self._ahora_utc()

        # ZeroMQ
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.connect(f"tcp://{broker_ip}:{broker_puerto}")

        # Semáforo
        self.semaforo = Semaforo(
            interseccion_id=f"INT_{M}{N}",
            fase_inicial=fase_inicial,
            duracion_normal=duracion_semaforo,
            offset_inicial=offset_inicial,
        )

        # Sensores
        self.Camara = Camara("", [M, N], intervalo_camara, self.socket, 0, 0,0,0)
        self.GPS = GPS("", [M, N], intervalo_gps, self.socket, 0, "NORMAL")
        self.Espira_inductiva = Espira_inductiva(
            "", [M, N], intervalo_espira, self.socket, 0, intervalo_espira, None, None
        )

        self.Camara.Generar_id(self.M, self.N)
        self.GPS.Generar_id(self.M, self.N)
        self.Espira_inductiva.Generar_id(self.M, self.N)

        self.thread = threading.Thread(target=self._run, daemon=True)

        self._ultimo_envio_camara = 0.0
        self._ultimo_envio_gps = 0.0
        self._ultimo_envio_espira = 0.0
        self._ultimo_log = 0.0

    def _ahora_utc(self):
        return datetime.now(timezone.utc)

    def _llegadas_por_segundo(self):
        """
        Llegadas pequeñas y calibradas para que la ciudad normal no colapse tan rápido.
        """
        if self.demanda == "baja":
            # promedio bajo
            llegadas_h = random.choices([0, 1, 2], weights=[0.45, 0.40, 0.15], k=1)[0]
            llegadas_v = random.choices([0, 1, 2], weights=[0.45, 0.40, 0.15], k=1)[0]
        elif self.demanda == "media":
            # promedio medio
            llegadas_h = random.choices([0, 1, 2, 3], weights=[0.15, 0.35, 0.35, 0.15], k=1)[0]
            llegadas_v = random.choices([0, 1, 2, 3], weights=[0.15, 0.35, 0.35, 0.15], k=1)[0]
        else:
            # promedio alto
            llegadas_h = random.choices([1, 2, 3, 4], weights=[0.15, 0.35, 0.30, 0.20], k=1)[0]
            llegadas_v = random.choices([1, 2, 3, 4], weights=[0.15, 0.35, 0.30, 0.20], k=1)[0]

        return llegadas_h, llegadas_v

    def _capacidad_salida(self, direccion, estado_sem):
        """
        Cuántos carros pueden cruzar por segundo cuando tienen verde.
        """
        if estado_sem["modo_prioridad"] and estado_sem["direccion_prioritaria"] == direccion:
            return random.randint(5, 7)

        return random.randint(3, 6)

    def _recalcular_metricas(self):
        cola_max = max(self.cola_horizontal, self.cola_vertical)
        cola_total = self.cola_horizontal + self.cola_vertical

        # Velocidad derivada de la carga real del cruce
        if cola_max <= 3 and cola_total <= 6:
            self.velocidad_promedio = random.randint(40, 50) #alta velocidad, valores bajos en las colas 
        elif cola_max <= 8 and cola_total <= 14:
            self.velocidad_promedio = random.randint(28, 39) 
        elif cola_max <= 15 and cola_total <= 28:
            self.velocidad_promedio = random.randint(15, 27)
        else:
            self.velocidad_promedio = random.randint(5, 14)

        # Nivel de congestión según velocidad (alineado con la idea del enunciado)
        if self.velocidad_promedio <= 10:
            self.nivel_congestion = "ALTA"
        elif self.velocidad_promedio >= 40:
            self.nivel_congestion = "BAJA"
        else:
            self.nivel_congestion = "NORMAL"

        estado_sem = self.semaforo.obtener_estado()

        if estado_sem["modo_prioridad"]:
            self.estado_trafico = "PRIORIZACION"
        elif cola_max >= 12 or cola_total >= 24 or self.velocidad_promedio <= 12:
            self.estado_trafico = "CONGESTION"
        else:
            self.estado_trafico = "NORMAL"

    def _simular_un_tick(self):
        llegadas_h, llegadas_v = self._llegadas_por_segundo()
        estado_sem = self.semaforo.obtener_estado()

        with self.lock:
            # Siempre llegan carros a ambas corrientes
            self.cola_horizontal += llegadas_h
            self.cola_vertical += llegadas_v

            pasan_h = 0
            pasan_v = 0

            if estado_sem["fase_actual"] == Semaforo.H_GREEN:
                capacidad = self._capacidad_salida("H", estado_sem)
                pasan_h = min(self.cola_horizontal, capacidad)
                self.cola_horizontal -= pasan_h
            else:
                capacidad = self._capacidad_salida("V", estado_sem)
                pasan_v = min(self.cola_vertical, capacidad)
                self.cola_vertical -= pasan_v

            self.vehiculos_espira_acumulados += (pasan_h + pasan_v)

            self._recalcular_metricas()

    def obtener_snapshot(self):
        estado_sem = self.semaforo.obtener_estado()
        with self.lock:
            return {
                "interseccion": f"INT_{self.M}{self.N}",
                "direccion_fila": self.direccion_fila,
                "direccion_columna": self.direccion_columna,
                "demanda": self.demanda,
                "cola_horizontal": self.cola_horizontal,
                "cola_vertical": self.cola_vertical,
                "cola_max": max(self.cola_horizontal, self.cola_vertical),
                "cola_total": self.cola_horizontal + self.cola_vertical,
                "velocidad_promedio": self.velocidad_promedio,
                "nivel_congestion": self.nivel_congestion,
                "estado_trafico": self.estado_trafico,
                "fase_actual": estado_sem["fase_actual"],
                "luz_horizontal": estado_sem["luz_horizontal"],
                "luz_vertical": estado_sem["luz_vertical"],
                "tiempo_restante": estado_sem["tiempo_restante"],
            }

    def _publicar_camara(self):
        snapshot = self.obtener_snapshot()
        self.Camara.Volumen = snapshot["cola_max"]
        self.Camara.Velocidad_promedio = snapshot["velocidad_promedio"]
        self.Camara.Cola_horizontal = snapshot["cola_horizontal"]
        self.Camara.Cola_vertical = snapshot["cola_vertical"]
        self.Camara.Envio_de_datos()

    def _publicar_gps(self):
        snapshot = self.obtener_snapshot()
        self.GPS.Velocidad_promedio = snapshot["velocidad_promedio"]
        self.GPS.Nivel_congestion = snapshot["nivel_congestion"]
        self.GPS.Envio_de_datos()

    def _publicar_espira(self):
        ahora = self._ahora_utc()

        with self.lock:
            vehiculos = self.vehiculos_espira_acumulados
            inicio = self.ventana_espira_inicio
            self.vehiculos_espira_acumulados = 0
            self.ventana_espira_inicio = ahora

        self.Espira_inductiva.Vehiculos_contados = vehiculos
        self.Espira_inductiva.Timestamp_inicio = inicio
        self.Espira_inductiva.Timestamp_final = ahora
        self.Espira_inductiva.Envio_de_datos()

    def _log_estado(self):
        s = self.obtener_snapshot()
        print(
            f"[{s['interseccion']}] "
            f"H={s['luz_horizontal']} | V={s['luz_vertical']} | "
            f"restan={s['tiempo_restante']:2d}s | "
            f"ColaH={s['cola_horizontal']:2d} | "
            f"ColaV={s['cola_vertical']:2d} | "
            f"Vel={s['velocidad_promedio']:2d} km/h | "
            f"Cong={s['nivel_congestion']} | "
            f"Estado={s['estado_trafico']} | "
            f"Demanda={s['demanda']}"
        )

    def _run(self):
        time.sleep(1)  # para estabilizar PUB/SUB

        self._ultimo_envio_camara = time.monotonic()
        self._ultimo_envio_gps = time.monotonic()
        self._ultimo_envio_espira = time.monotonic()
        self._ultimo_log = time.monotonic()

        while not self.stop_event.is_set():
            inicio_tick = time.monotonic()

            self._simular_un_tick()

            ahora = time.monotonic()

            if ahora - self._ultimo_envio_camara >= self.intervalo_camara:
                self._publicar_camara()
                self._ultimo_envio_camara = ahora

            if ahora - self._ultimo_envio_gps >= self.intervalo_gps:
                self._publicar_gps()
                self._ultimo_envio_gps = ahora

            if ahora - self._ultimo_envio_espira >= self.intervalo_espira:
                self._publicar_espira()
                self._ultimo_envio_espira = ahora

            if ahora - self._ultimo_log >= self.log_intervalo:
                self._log_estado()
                self._ultimo_log = ahora

            cambio = self.semaforo.tick(self.tick_segundos)
            if cambio:
                estado = self.semaforo.obtener_estado()
                print(
                    f"🚦 [{estado['interseccion_id']}] Cambio -> "
                    f"H={estado['luz_horizontal']} / V={estado['luz_vertical']} "
                    f"({estado['tiempo_restante']}s)"
                )

            duracion_tick = time.monotonic() - inicio_tick
            restante = self.tick_segundos - duracion_tick
            if restante > 0:
                self.stop_event.wait(restante)

    def iniciar(self):
        if not self.thread.is_alive():
            self.thread.start()

    def detener(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def forzar_prioridad_horizontal(self, duracion=20):
        self.semaforo.forzar_horizontal(duracion)

    def forzar_prioridad_vertical(self, duracion=20):
        self.semaforo.forzar_vertical(duracion)

    def Mostrar_IDS(self):
        estado = self.semaforo.obtener_estado()
        print(
            f"Intersección {self.M}{self.N} | "
            f"Fila={self.direccion_fila} | Col={self.direccion_columna} | "
            f"Demanda={self.demanda} | "
            f"H={estado['luz_horizontal']} / V={estado['luz_vertical']} | "
            f"restan={estado['tiempo_restante']}s"
        )
        print(f"Camara:           {self.Camara.get_Sensor_id()}")
        print(f"GPS:              {self.GPS.get_Sensor_id()}")
        print(f"Espira_inductiva: {self.Espira_inductiva.get_Sensor_id()}")