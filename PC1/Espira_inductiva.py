from Sensores import Sensores

class Espira_inductiva(Sensores):
    def __init__(self, Sensor_id, Interseccion, Timespant, Broker_puerto, Vehiculos_contados, Intervalo_segundos, Timestamp_inicio, Timestamp_final):
        super().__init__(Sensor_id, None, Interseccion, Timespant, Broker_puerto)
        self.Vehiculos_contados = Vehiculos_contados
        self.Intervalo_segundos = Intervalo_segundos
        self.Timespant_inicio = Timestamp_inicio
        self.Timespant_final = Timestamp_final
        self.set_Tipo_sensor("Espira_inductiva")

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"EspIn-EI{M}{N}")