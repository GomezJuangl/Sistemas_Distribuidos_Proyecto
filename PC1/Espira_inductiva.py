from Sensores import Sensores

class Espira_inductiva(Sensores):
    def __init__(self, Sensor_id, Tipo_sensor, Interseccion, Timespant, Broker_puerto, Vehiculos_contados, Intervalo_segundos, Timestamp_inicio, Timestamp_final):

        super().__init__(Sensor_id, Tipo_sensor, Interseccion, Timespant, Broker_puerto)

        self.Vehiculos_contados = Vehiculos_contados
        self.Intervalo_segundos = Intervalo_segundos
        self.Timespant_inicio = Timestamp_inicio
        self.Timespant_final = Timestamp_final
    
    def Asignar_Tipo_sensor(self):
        self.Tipo_sensor = "Espira Inductiva"

    def Generar_id(self,M,N,i):
        self.Sensor_id = f"EspIn{i} EI{M}{N}"