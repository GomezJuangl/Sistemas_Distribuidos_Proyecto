import json
import threading
import time
import sqlite3
from datetime import datetime, timedelta
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
        self.BD_PRINCIPAL_HEALTH_PUERTO = 7003
        self.BD_PRINCIPAL_SYNC_PUERTO = 7004

        self.BD_REPLICA_IP = "127.0.0.1"
        self.BD_REPLICA_PUERTO = 7002
        self.BD_REPLICA_DB = "BaseDatosReplica/bd_replica.db"

        # Estado de PC3
        self.pc3_activo = True
        self.timestamp_caida_pc3 = None
        self.pc3_syncing = False          # True mientras sincronizar_bd esta en ejecucion
        self.lock_pc3_estado = threading.Lock()

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

            # El timestamp de decisión debe ser único por evento para principal y replica.
            timestamp_decision = datetime.now().isoformat()

            self.imprimir_resumen(interseccion, evento, estado_trafico, accion)
            self.enviar_comando_control(interseccion, accion)

            # Primero persistir en replica (fuente de verdad para re-sync).
            self.enviar_bd(
                self.socket_push_bd_replica, self.lock_bd_replica,
                interseccion, evento, estado_trafico, accion, timestamp_decision, "BD replica"
            )

            # Enviar a BD principal solo si PC3 esta activo.
            if self.pc3_activo:
                self.enviar_bd(
                    self.socket_push_bd_principal, self.lock_bd_principal,
                    interseccion, evento, estado_trafico, accion, timestamp_decision, "BD principal"
                )

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
    
    def _enviar(self, socket, lock, mensaje, nombre, no_bloqueante=True):
        """Envío thread-safe: protege el socket con un lock."""
        with lock:
            try:
                if no_bloqueante:
                    socket.send_string(mensaje, zmq.NOBLOCK)
                else:
                    socket.send_string(mensaje)
            except zmq.Again:
                print(f"⚠️ {nombre} no disponible, mensaje descartado")

    def enviar_bd(self, socket, lock, interseccion, evento, estado_trafico, accion, timestamp_decision, nombre):
        mensaje = json.dumps({
            "evento": evento,
            "interseccion": interseccion,
            "estado_trafico": estado_trafico,
            "accion": accion,
            "timestamp": timestamp_decision
        })
        # Para BD priorizamos confiabilidad sobre descarte.
        self._enviar(socket, lock, mensaje, nombre, no_bloqueante=False)

    def enviar_comando_control(self, interseccion, accion):
        # Solo enviar al servicio de control cuando hay una accion real sobre el semaforo
        if accion not in ("FORZAR_HORIZONTAL", "FORZAR_VERTICAL"):
            return

        if self.socket_push_control is None:
            print("[CONTROL] socket_push_control no inicializado")
            return

        payload = {
            "interseccion": interseccion,
            "accion": accion,
            "duracion": 20,
            "timestamp": datetime.now().isoformat(),
            "origen": "servicio_analitica"
        }

        try:
            self.socket_push_control.send_string(json.dumps(payload), zmq.NOBLOCK)
            print(f"🚦 [CONTROL] Enviado al servicio de semaforos -> Interseccion={interseccion} | Accion={accion}")
        except zmq.Again:
            print(f"⚠️ [CONTROL] No se pudo enviar comando para {interseccion}")

    def forzar_prioridad(self, interseccion, eje, duracion):
        accion = "FORZAR_HORIZONTAL" if eje == "H" else "FORZAR_VERTICAL"
        print(f"🚑 [PRIORIDAD MANUAL] Interseccion={interseccion} | Eje={eje} | Duracion={duracion}s")

        if self.socket_push_control is None:
            print("[PRIORIDAD MANUAL] socket_push_control no inicializado")
            return

        payload = {
            "interseccion": interseccion,
            "accion": accion,
            "duracion": duracion,
            "timestamp": datetime.now().isoformat(),
            "origen": "monitoreo_prioridad_manual"
        }

        try:
            self.socket_push_control.send_string(json.dumps(payload), zmq.NOBLOCK)
            print(f"🚑 [PRIORIDAD MANUAL] Comando enviado al servicio de semaforos")
        except zmq.Again:
            print(f"⚠️ [PRIORIDAD MANUAL] No se pudo enviar comando para {interseccion}")

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

    # HEALTH CHECK Y TOLERANCIA A FALLAS

    def health_check_pc3(self):
        """Cada 5 segundos hace ping a PC3. Si no responde, marca pc3_activo=False."""
        HEALTH_TIMEOUT = 3000  # ms
        INTERVALO = 5  # segundos

        print(f"🚨🚨🚨🚨🚨 [HEALTH CHECK] Iniciado. Ping a PC3 cada {INTERVALO}s (timeout {HEALTH_TIMEOUT}ms) 🚨🚨🚨🚨🚨")

        while True:
            socket_ping = self.contexto.socket(zmq.REQ)
            socket_ping.setsockopt(zmq.RCVTIMEO, HEALTH_TIMEOUT)
            socket_ping.setsockopt(zmq.LINGER, 0)
            socket_ping.connect(f"tcp://{self.BD_PRINCIPAL_IP}:{self.BD_PRINCIPAL_HEALTH_PUERTO}")

            with self.lock_pc3_estado:
                estado_anterior = self.pc3_activo

            try:
                socket_ping.send_string("PING")
                respuesta = socket_ping.recv_string()

                if respuesta == "PONG":
                    iniciar_sync = False
                    with self.lock_pc3_estado:
                        self.pc3_activo = True
                        # Lanzar sync solo si PC3 acaba de volver Y no hay sync en curso
                        if not estado_anterior and not self.pc3_syncing:
                            self.pc3_syncing = True
                            iniciar_sync = True

                    if iniciar_sync:
                        print("✅✅✅✅✅ [HEALTH CHECK] PC3 recuperado. Iniciando sincronizacion... ✅✅✅✅✅")
                        threading.Thread(target=self.sincronizar_bd, daemon=True).start()

            except zmq.Again:
                # Timeout: PC3 no respondio
                with self.lock_pc3_estado:
                    if self.pc3_activo:
                        self.timestamp_caida_pc3 = datetime.now().isoformat()
                        print(f"🔴🔴🔴🔴🔴 [HEALTH CHECK] PC3 NO RESPONDE. Marcado como caido. Timestamp: {self.timestamp_caida_pc3} 🔴🔴🔴🔴🔴")
                    self.pc3_activo = False

            except Exception as e:
                with self.lock_pc3_estado:
                    if self.pc3_activo:
                        self.timestamp_caida_pc3 = datetime.now().isoformat()
                    self.pc3_activo = False
                print(f"❌❌❌❌❌ [HEALTH CHECK] Error: {e} ❌❌❌❌❌")

            finally:
                socket_ping.close()

            time.sleep(INTERVALO)

    def sincronizar_bd(self):
        """Lee datos de la replica desde timestamp_caida y los envia a PC3 por PUSH."""
        # Snapshot del timestamp dentro del lock para evitar condicion de carrera
        with self.lock_pc3_estado:
            ts_caida = self.timestamp_caida_pc3

        if ts_caida is None:
            print("🔄🔄🔄🔄🔄 [SYNC] No hay timestamp de caida, no se puede sincronizar 🔄🔄🔄🔄🔄")
            with self.lock_pc3_estado:
                self.pc3_syncing = False
            return

        # Margen de seguridad: 10 segundos antes de la caida detectada
        timestamp_con_margen = (
            datetime.fromisoformat(ts_caida) - timedelta(seconds=10)
        ).isoformat()

        print(f"🔄🔄🔄🔄🔄 [SYNC] Iniciando. Caida detectada: {ts_caida} 🔄🔄🔄🔄🔄")
        print(f"🔄🔄🔄🔄🔄 [SYNC] Leyendo replica desde: {timestamp_con_margen} 🔄🔄🔄🔄🔄")

        try:
            con = sqlite3.connect(self.BD_REPLICA_DB)
            registros_sync = []

            # GPS
            rows = con.execute(
                "SELECT ID, TIPO_SENSOR, INTERSECCION, NIVEL_CONGESTION, VELOCIDAD_PROMEDIO, TIMESTAMP FROM GPS WHERE TIMESTAMP >= ?",
                (timestamp_con_margen,)
            ).fetchall()
            n_gps = len(rows)
            for r in rows:
                registros_sync.append({
                    "sync_tipo": "sensor",
                    "evento": {
                        "sensor_id": r[0].rsplit("_", 1)[0],
                        "tipo_sensor": r[1],
                        "interseccion": r[2],
                        "nivel_congestion": r[3],
                        "velocidad_promedio": r[4],
                        "timestamp": r[5],
                    },
                })

            # Camara
            rows = con.execute(
                "SELECT ID, TIPO_SENSOR, INTERSECCION, VOLUMEN, VELOCIDAD_PROMEDIO, COLA_HORIZONTAL, COLA_VERTICAL, TIMESTAMP FROM CAMARA WHERE TIMESTAMP >= ?",
                (timestamp_con_margen,)
            ).fetchall()
            n_cam = len(rows)
            for r in rows:
                registros_sync.append({
                    "sync_tipo": "sensor",
                    "evento": {
                        "sensor_id": r[0].rsplit("_", 1)[0],
                        "tipo_sensor": r[1],
                        "interseccion": r[2],
                        "volumen": r[3],
                        "velocidad_promedio": r[4],
                        "cola_horizontal": r[5],
                        "cola_vertical": r[6],
                        "timestamp": r[7],
                    },
                })

            # Espira
            rows = con.execute(
                "SELECT ID, TIPO_SENSOR, INTERSECCION, VEHICULOS_CONTADOS, INTERVALO_SEGUNDOS, TIMESTAMP_INICIO, TIMESTAMP_FIN FROM ESPIRA WHERE TIMESTAMP_FIN >= ?",
                (timestamp_con_margen,)
            ).fetchall()
            n_esp = len(rows)
            for r in rows:
                registros_sync.append({
                    "sync_tipo": "sensor",
                    "evento": {
                        "sensor_id": r[0].rsplit("_", 1)[0],
                        "tipo_sensor": r[1],
                        "interseccion": r[2],
                        "vehiculos_contados": r[3],
                        "intervalo_segundos": r[4],
                        "timestamp_inicio": r[5],
                        "timestamp_fin": r[6],
                    },
                })

            # Decisiones
            rows = con.execute(
                "SELECT INTERSECCION, ESTADO_TRAFICO, ACCION, TIMESTAMP FROM DECISIONES WHERE TIMESTAMP >= ?",
                (timestamp_con_margen,)
            ).fetchall()
            n_dec = len(rows)
            for r in rows:
                registros_sync.append({
                    "sync_tipo": "decision",
                    "interseccion": r[0],
                    "estado_trafico": r[1],
                    "accion": r[2],
                    "timestamp": r[3],
                })

            con.close()

            print(f"🔄🔄🔄🔄🔄 [SYNC] Registros a enviar: GPS={n_gps} CAM={n_cam} ESP={n_esp} DEC={n_dec} TOTAL={len(registros_sync)} 🔄🔄🔄🔄🔄")

            if not registros_sync:
                print("🔄🔄🔄🔄🔄 [SYNC] No hay datos pendientes de sincronizar 🔄🔄🔄🔄🔄")
                with self.lock_pc3_estado:
                    self.timestamp_caida_pc3 = None
                    self.pc3_syncing = False
                return

            socket_sync = self.contexto.socket(zmq.PUSH)
            socket_sync.setsockopt(zmq.LINGER, 30000)   # 30s para asegurar entrega completa
            socket_sync.setsockopt(zmq.SNDHWM, 10000)   # buffer grande: evita bloqueos en el loop
            socket_sync.connect(f"tcp://{self.BD_PRINCIPAL_IP}:{self.BD_PRINCIPAL_SYNC_PUERTO}")

            time.sleep(1)

            for registro in registros_sync:
                socket_sync.send_string(json.dumps(registro))

            print(f"🔄🔄🔄🔄🔄 [SYNC] {len(registros_sync)} mensajes enviados al buffer ZMQ. Cerrando socket... 🔄🔄🔄🔄🔄")
            socket_sync.close()  # espera hasta 30s para que TCP entregue todo a PC3
            print("✅✅✅✅✅ [SYNC] Socket cerrado. PC3 procesara los registros en background. ✅✅✅✅✅")

            with self.lock_pc3_estado:
                self.timestamp_caida_pc3 = None
                self.pc3_syncing = False

        except Exception as e:
            print(f"❌❌❌❌❌ [SYNC] Error durante sincronizacion: {e} ❌❌❌❌❌")
            with self.lock_pc3_estado:
                self.pc3_syncing = False

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
            threading.Thread(target=self.health_check_pc3, daemon=True).start()
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
