import threading


class Semaforo:
    H_GREEN = "H_GREEN"   # Horizontal verde, vertical rojo
    V_GREEN = "V_GREEN"   # Vertical verde, horizontal rojo

    def __init__(self, interseccion_id, fase_inicial="H_GREEN", duracion_normal=15, offset_inicial=0):
        self.interseccion_id = interseccion_id
        self.duracion_normal = duracion_normal
        self.lock = threading.Lock() 

        self.modo_prioridad = False
        self.direccion_prioritaria = None  # "H" o "V"

        self.fase_actual = fase_inicial
        self.luz_horizontal = "ROJO"
        self.luz_vertical = "ROJO"
        self._aplicar_fase(self.fase_actual) 

        # Desfase inicial para que no cambien todos al mismo tiempo
        self.tiempo_restante = max(1, self.duracion_normal - offset_inicial)

    def _aplicar_fase(self, fase):
        self.fase_actual = fase
        if fase == self.H_GREEN:
            self.luz_horizontal = "VERDE"
            self.luz_vertical = "ROJO"
        else:
            self.luz_horizontal = "ROJO"
            self.luz_vertical = "VERDE"

    def tick(self, segundos=1):
    
        with self.lock:
            self.tiempo_restante -= segundos

            if self.tiempo_restante > 0:
                return False

            if self.modo_prioridad:
                self.modo_prioridad = False
                self.direccion_prioritaria = None

            if self.fase_actual == self.H_GREEN:
                self._aplicar_fase(self.V_GREEN)
            else:
                self._aplicar_fase(self.H_GREEN)

            self.tiempo_restante = self.duracion_normal
            return True

    def forzar_horizontal(self, duracion=20):
        with self.lock:
            self.modo_prioridad = True
            self.direccion_prioritaria = "H"
            self._aplicar_fase(self.H_GREEN)
            self.tiempo_restante = duracion

    def forzar_vertical(self, duracion=20):
        with self.lock:
            self.modo_prioridad = True
            self.direccion_prioritaria = "V"
            self._aplicar_fase(self.V_GREEN)
            self.tiempo_restante = duracion

    def obtener_estado(self):
        with self.lock:
            return {
                "interseccion_id": self.interseccion_id,
                "fase_actual": self.fase_actual,
                "luz_horizontal": self.luz_horizontal,
                "luz_vertical": self.luz_vertical,
                "tiempo_restante": self.tiempo_restante,
                "modo_prioridad": self.modo_prioridad,
                "direccion_prioritaria": self.direccion_prioritaria,
            }