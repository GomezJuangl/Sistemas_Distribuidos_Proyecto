from Sensores.Sensores import Sensores
import json
from datetime import datetime, timedelta


class Espira_inductiva(Sensores):
    def __init__(self,Sensor_id,Interseccion,Timespant,socket,Vehiculos_contados,Intervalo_segundos,Timestamp_inicio,Timestamp_final,):
        super().__init__(Sensor_id, "Espira_inductiva", Interseccion, Timespant, socket)
        self.Vehiculos_contados = Vehiculos_contados
        self.Intervalo_segundos = Intervalo_segundos
        self.Timestamp_inicio = Timestamp_inicio
        self.Timestamp_final = Timestamp_final

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"ESP-{M}{N}")

    def Calcular_Timestamp_intervalo(self):
        """Usa el intervalo definido por la intersección; si no existe, lo calcula."""
        if self.Timestamp_inicio and self.Timestamp_final:
            inicio = self.Timestamp_inicio.isoformat()
            fin = self.Timestamp_final.isoformat()
            return inicio, fin

        inicio = datetime.now()
        fin = inicio + timedelta(seconds=self.Intervalo_segundos)
        return inicio.isoformat(), fin.isoformat()

    def Envio_de_datos(self):
        inicio, fin = self.Calcular_Timestamp_intervalo()

        evento = {
            "sensor_id": self.Sensor_id,
            "tipo_sensor": "espira_inductiva",
            "interseccion": f"INT_{self.Interseccion[0]}{self.Interseccion[1]}",
            "vehiculos_contados": self.Vehiculos_contados,
            "intervalo_segundos": self.Intervalo_segundos,
            "timestamp_inicio": inicio,
            "timestamp_fin": fin,
        }
        mensaje = json.dumps(evento)
        print(f"🌀 [ENVÍO] {self.Sensor_id}: {mensaje}")
        self.socket.send_string(f"espira_inductiva {mensaje}")