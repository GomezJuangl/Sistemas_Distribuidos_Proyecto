import json
import threading
from datetime import datetime
import zmq


class ServicioAnalitica:
    def __init__(self):
        
        # CONFIGURACION
        self.BROKER_IP = "127.0.0.1"
        self.BROKER_PUERTO = 5556   

        self.TOPIC_CAMARA = "camara"
        self.TOPIC_ESPIRA = "espira_inductiva"
        self.TOPIC_GPS = "gps"

        self.CONTROL_IP = "127.0.0.1"
        self.CONTROL_PUERTO = 6001

        self.SEMAFOROS_PUSH_IP = "127.0.0.1"
        self.SEMAFOROS_PUSH_PUERTO = 6002

        self.BD_PRINCIPAL_IP = "127.0.0.1"
        self.BD_PRINCIPAL_PUERTO = 7001

        self.BD_REPLICA_IP = "127.0.0.1"
        self.BD_REPLICA_PUERTO = 7002

        # UMBRALES 
        self.umbral_volumen_congestion = 15
        self.umbral_velocidad_baja = 10
        self.umbral_vehiculos_espira = 60
        self.umbral_diferencia_colas = 3

        # ESTADO INTERNO
        self.estado_intersecciones = {}
        self.inicializar_estado_intersecciones()

        # ZMQ    
        self.contexto = zmq.Context()
        self.socket_sub_broker = None
        self.socket_push_bd_principal = None
        self.socket_push_bd_replica = None
        self.socket_rep_monitoreo = None
        self.socket_push_control = None
        # Locks para proteger sockets compartidos entre hilos
        self.lock_bd_principal = threading.Lock()
        self.lock_bd_replica = threading.Lock()

    # INICIALIZACION
    
    def inicializar_estado_intersecciones(self):
        letras = ["A", "B", "C", "D"]
        for letra in letras:
            for numero in range(1, 5):
                interseccion = f"INT_{letra}{numero}"
                self.estado_intersecciones[interseccion] = {
                    "camara": None,
                    "gps": None,
                    "espira": None,
                    "estado_actual": "SIN_DATOS",
                    "eje_congestionado": None,
                    "ultima_decision": "SIN_ACCION",
                    "ultima_actualizacion": None,
                }

    def imprimir_reglas(self):
        print("=" * 75)
        print("[ANALITICA] REGLAS DE CLASIFICACION DE TRAFICO")
        print("=" * 75)
        print(f"  TRAFICO NORMAL:")
        print(f"    Volumen (cola max)    < {self.umbral_volumen_congestion} vehiculos")
        print(f"    Velocidad promedio    > {self.umbral_velocidad_baja} km/h")
        print(f"    Congestion GPS       != ALTA")
        print(f"    Vehiculos espira     < {self.umbral_vehiculos_espira} vehiculos/ciclo")
        print(f"  CONGESTION (se activa si ANY condicion se cumple):")
        print(f"    Volumen (cola max)   >= {self.umbral_volumen_congestion} vehiculos")
        print(f"    Velocidad promedio   <= {self.umbral_velocidad_baja} km/h")
        print(f"    Congestion GPS       == ALTA")
        print(f"    Vehiculos espira    >= {self.umbral_vehiculos_espira} vehiculos/ciclo")
        print(f"  CONGESTION DIRECCIONAL:")
        print(f"    Diferencia entre colas H y V >= {self.umbral_diferencia_colas} -> se identifica eje congestionado")
        print(f"  PRIORIZACION:")
        print(f"    Comando manual desde el servicio de monitoreo (ej: paso de ambulancia)")
        print("=" * 75)

    def conectar(self):
        # SUB: recibe del broker (con suscripción por tópicos)
        self.socket_sub_broker = self.contexto.socket(zmq.SUB)
        self.socket_sub_broker.connect(f"tcp://{self.BROKER_IP}:{self.BROKER_PUERTO}")
        self.socket_sub_broker.setsockopt_string(zmq.SUBSCRIBE, self.TOPIC_CAMARA)
        self.socket_sub_broker.setsockopt_string(zmq.SUBSCRIBE, self.TOPIC_GPS)
        self.socket_sub_broker.setsockopt_string(zmq.SUBSCRIBE, self.TOPIC_ESPIRA)
        print(f"[ANALITICA] Conectada al broker en tcp://{self.BROKER_IP}:{self.BROKER_PUERTO}")
        print(f"[ANALITICA] Suscrita a tópicos: {self.TOPIC_CAMARA}, {self.TOPIC_GPS}, {self.TOPIC_ESPIRA}")

        # PUSH: envia a BD principal (PC3)
        self.socket_push_bd_principal = self.contexto.socket(zmq.PUSH)
        self.socket_push_bd_principal.connect(f"tcp://{self.BD_PRINCIPAL_IP}:{self.BD_PRINCIPAL_PUERTO}")
        print(f"[ANALITICA] Conectada a BD principal en tcp://{self.BD_PRINCIPAL_IP}:{self.BD_PRINCIPAL_PUERTO}")

        # PUSH: envia a BD replica (PC2)
        self.socket_push_bd_replica = self.contexto.socket(zmq.PUSH)
        self.socket_push_bd_replica.connect(f"tcp://{self.BD_REPLICA_IP}:{self.BD_REPLICA_PUERTO}")
        print(f"[ANALITICA] Conectada a BD replica en tcp://{self.BD_REPLICA_IP}:{self.BD_REPLICA_PUERTO}")

        # REP: recibe indicaciones directas del monitoreo (PC3)
        self.socket_rep_monitoreo = self.contexto.socket(zmq.REP)
        self.socket_rep_monitoreo.bind(f"tcp://*:{self.CONTROL_PUERTO}")
        print(f"[ANALITICA] REP escuchando en tcp://*:{self.CONTROL_PUERTO}")

        # PUSH: envia al servicio de control de semaforos (PC2)
        self.socket_push_control = self.contexto.socket(zmq.PUSH)
        self.socket_push_control.connect(f"tcp://{self.SEMAFOROS_PUSH_IP}:{self.SEMAFOROS_PUSH_PUERTO}")
        print(f"[ANALITICA] Conectada a control de semaforos en tcp://{self.SEMAFOROS_PUSH_IP}:{self.SEMAFOROS_PUSH_PUERTO}")

    # LOOP PRINCIPAL
    
    def recibir_eventos(self):
        while True:
            mensaje_raw = self.socket_sub_broker.recv_string()
            evento = self.parsear_evento(mensaje_raw)

            if evento is None:
                continue

            self.actualizar_estado_interseccion(evento)

            interseccion = evento["interseccion"]
            estado_trafico, eje_congestionado = self.evaluar_estado_trafico(interseccion)
            accion = self.decidir_accion_semaforo(interseccion, estado_trafico, eje_congestionado)

            self.estado_intersecciones[interseccion]["estado_actual"] = estado_trafico
            self.estado_intersecciones[interseccion]["eje_congestionado"] = eje_congestionado
            self.estado_intersecciones[interseccion]["ultima_decision"] = accion

            self.imprimir_resumen(interseccion, evento, estado_trafico, accion)
            self.enviar_comando_control(interseccion, accion)

            # Enviar a BDs en hilos separados para no bloquear (con locks)
            threading.Thread(
                target=self.enviar_bd,
                args=(self.socket_push_bd_principal, self.lock_bd_principal,
                      interseccion, evento, estado_trafico, accion, "BD principal")
            ).start()
            threading.Thread(
                target=self.enviar_bd,
                args=(self.socket_push_bd_replica, self.lock_bd_replica,
                      interseccion, evento, estado_trafico, accion, "BD replica")
            ).start()

    # ESCUCHAR MONITOREO (hilo aparte)

    def escuchar_monitoreo(self):
        print("[ANALITICA] Hilo de monitoreo activo, esperando comandos...")
        while True:
            mensaje = self.socket_rep_monitoreo.recv_string()
            print(f"[ANALITICA] Comando recibido del monitoreo: {mensaje}")
            try:
                comando = json.loads(mensaje)
                if comando.get("tipo") == "prioridad":
                    interseccion = comando["interseccion"]
                    eje = comando["eje"]
                    duracion = comando["duracion"]
                    self.forzar_prioridad(interseccion, eje, duracion)
                    self.socket_rep_monitoreo.send_string(
                        f"OK: Ola verde activada en {interseccion} eje {eje} por {duracion}s"
                    )
                else:
                    self.socket_rep_monitoreo.send_string("Comando no reconocido")
            except Exception as e:
                self.socket_rep_monitoreo.send_string(f"Error: {e}")

    # PARSING Y ACTUALIZACION
    
    def parsear_evento(self, mensaje_raw):
        """Separa el tópico del JSON y parsea el evento."""
        try:
            partes = mensaje_raw.split(" ", 1)
            if len(partes) < 2:
                print(f"[ANALITICA] Mensaje sin tópico válido: {mensaje_raw[:60]}")
                return None

            topico = partes[0]
            json_str = partes[1]

            evento = json.loads(json_str)
            if "tipo_sensor" not in evento or "interseccion" not in evento:
                print("[ANALITICA] Evento incompleto:", evento)
                return None
            return evento
        except json.JSONDecodeError:
            print("[ANALITICA] Error parseando JSON:", mensaje_raw[:80])
            return None

    def actualizar_estado_interseccion(self, evento):
        interseccion = evento["interseccion"]

        if interseccion not in self.estado_intersecciones:
            print(f"[ANALITICA] Interseccion no reconocida: {interseccion}")
            return

        tipo_sensor = evento["tipo_sensor"]

        if tipo_sensor == "camara":
            self.estado_intersecciones[interseccion]["camara"] = evento
        elif tipo_sensor == "gps":
            self.estado_intersecciones[interseccion]["gps"] = evento
        elif tipo_sensor == "espira_inductiva":
            self.estado_intersecciones[interseccion]["espira"] = evento

        self.estado_intersecciones[interseccion]["ultima_actualizacion"] = datetime.now().isoformat()

    # LOGICA DE ANALISIS
    
    def evaluar_estado_trafico(self, interseccion):
        datos = self.estado_intersecciones[interseccion]

        evento_camara = datos["camara"]
        evento_gps = datos["gps"]
        evento_espira = datos["espira"]

        volumen_alto = False
        cola_alta = False
        gps_alta = False
        espira_alta = False
        velocidad_baja = False

        if evento_camara is not None:
            volumen = evento_camara.get("volumen", 0)
            velocidad_camara = evento_camara.get("velocidad_promedio", 50)
            cola_horizontal = evento_camara.get("cola_horizontal", 0)
            cola_vertical = evento_camara.get("cola_vertical", 0)

            if volumen >= self.umbral_volumen_congestion:
                volumen_alto = True
            if max(cola_horizontal, cola_vertical) >= self.umbral_volumen_congestion:
                cola_alta = True
            if velocidad_camara <= self.umbral_velocidad_baja:
                velocidad_baja = True

        if evento_gps is not None:
            nivel_congestion = evento_gps.get("nivel_congestion", "BAJA")
            velocidad_gps = evento_gps.get("velocidad_promedio", 50)

            if nivel_congestion == "ALTA":
                gps_alta = True
            if velocidad_gps <= self.umbral_velocidad_baja:
                velocidad_baja = True

        if evento_espira is not None:
            vehiculos = evento_espira.get("vehiculos_contados", 0)
            if vehiculos >= self.umbral_vehiculos_espira:
                espira_alta = True

        hay_congestion = volumen_alto or cola_alta or gps_alta or espira_alta or velocidad_baja

        if not hay_congestion:
            return "NORMAL", None

        eje_congestionado = self.determinar_eje_congestionado(interseccion)

        if eje_congestionado == "H":
            return "CONGESTION_HORIZONTAL", "H"
        if eje_congestionado == "V":
            return "CONGESTION_VERTICAL", "V"

        return "CONGESTION_GENERAL", None

    def determinar_eje_congestionado(self, interseccion):
        datos = self.estado_intersecciones[interseccion]
        evento_camara = datos["camara"]

        if evento_camara is None:
            return None

        cola_horizontal = evento_camara.get("cola_horizontal")
        cola_vertical = evento_camara.get("cola_vertical")

        if cola_horizontal is None or cola_vertical is None:
            return None

        diferencia = abs(cola_horizontal - cola_vertical)

        if diferencia < self.umbral_diferencia_colas:
            return None

        if cola_horizontal > cola_vertical:
            return "H"
        if cola_vertical > cola_horizontal:
            return "V"

        return None

    def decidir_accion_semaforo(self, interseccion, estado_trafico, eje_congestionado):
        if estado_trafico == "NORMAL":
            return "MANTENER_NORMAL"
        if estado_trafico == "CONGESTION_HORIZONTAL":
            return "FORZAR_HORIZONTAL"
        if estado_trafico == "CONGESTION_VERTICAL":
            return "FORZAR_VERTICAL"
        if estado_trafico == "CONGESTION_GENERAL":
            return "MARCAR_CONGESTION"
        if estado_trafico == "PRIORIZACION":
            if eje_congestionado == "H":
                return "FORZAR_HORIZONTAL"
            if eje_congestionado == "V":
                return "FORZAR_VERTICAL"
            return "PRIORIZACION_SIN_EJE"
        return "SIN_ACCION"

    # SALIDAS
    
    def _enviar(self, socket, lock, mensaje, nombre):
        """Envío thread-safe: protege el socket con un lock."""
        with lock:
            try:
                socket.send_string(mensaje, zmq.NOBLOCK)
            except zmq.Again:
                print(f"⚠️ {nombre} no disponible, mensaje descartado")

    def enviar_bd(self, socket, lock, interseccion, evento, estado_trafico, accion, nombre):
        mensaje = json.dumps({
            "evento": evento,
            "interseccion": interseccion,
            "estado_trafico": estado_trafico,
            "accion": accion,
            "timestamp": datetime.now().isoformat()
        })
        self._enviar(socket, lock, mensaje, nombre)

    def enviar_comando_control(self, interseccion, accion):
        if self.socket_push_control is None:
            print("[CONTROL] socket_push_control no inicializado")
            return

        payload = {
            "interseccion": interseccion,
            "accion": accion,
            "duracion": 20 if "FORZAR" in accion else 15,
            "timestamp": datetime.now().isoformat(),
            "origen": "servicio_analitica"
        }

        try:
            self.socket_push_control.send_string(json.dumps(payload), zmq.NOBLOCK)
            print(f"[CONTROL] Interseccion={interseccion} | Accion={accion}")
        except zmq.Again:
            print(f"⚠️ [CONTROL] No se pudo enviar comando para {interseccion}")

    def forzar_prioridad(self, interseccion, eje, duracion):
        print(f"[PRIORIDAD MANUAL] Interseccion={interseccion} | Eje={eje} | Duracion={duracion}")

    # LOGS
    
    def imprimir_resumen(self, interseccion, evento, estado_trafico, accion):
        tipo = evento.get("tipo_sensor", "?")
        linea = f"[ANALITICA] {interseccion} | Sensor: {tipo} | Estado: {estado_trafico} | Accion: {accion}"

        if estado_trafico != "NORMAL":
            # Solo imprime detalle cuando hay congestión
            datos = self.estado_intersecciones[interseccion]
            detalle = ""
            if datos["camara"] is not None:
                cam = datos["camara"]
                detalle += f" | Cam: vol={cam.get('volumen')} vel={cam.get('velocidad_promedio')} colaH={cam.get('cola_horizontal')} colaV={cam.get('cola_vertical')}"
            if datos["gps"] is not None:
                gps = datos["gps"]
                detalle += f" | GPS: vel={gps.get('velocidad_promedio')} nivel={gps.get('nivel_congestion')}"
            if datos["espira"] is not None:
                esp = datos["espira"]
                detalle += f" | Esp: veh={esp.get('vehiculos_contados')}"
            print(f"⚠️  {linea}{detalle}")
        else:
            print(f"✅ {linea}")

    # CIERRE
    
    def cerrar(self):
        if self.socket_sub_broker is not None:
            self.socket_sub_broker.close()
        if self.socket_push_bd_principal is not None:
            self.socket_push_bd_principal.close()
        if self.socket_push_bd_replica is not None:
            self.socket_push_bd_replica.close()
        if self.socket_rep_monitoreo is not None:
            self.socket_rep_monitoreo.close()
        if self.socket_push_control is not None:
            self.socket_push_control.close()
        self.contexto.term()

    def ejecutar(self):
        try:
            self.imprimir_reglas()
            self.conectar()
            threading.Thread(target=self.escuchar_monitoreo, daemon=True).start()
            self.recibir_eventos()
        except KeyboardInterrupt:
            print("\n[ANALITICA] Servicio detenido por el usuario")
        finally:
            self.cerrar()


def main():
    servicio = ServicioAnalitica()
    servicio.ejecutar()


if __name__ == "__main__":
    main()