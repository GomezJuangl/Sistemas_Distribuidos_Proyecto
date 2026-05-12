import json
import threading
import zmq


class ReceptorControlSemaforos:
    def __init__(self, ciudad, puerto=6003):
        self.ciudad = ciudad
        self.puerto = puerto

        self.contexto = zmq.Context()
        self.socket_rep = self.contexto.socket(zmq.REP)
        self.socket_rep.bind(f"tcp://*:{self.puerto}")

        self.hilo = threading.Thread(target=self._run, daemon=True)
        self.activo = False

    def iniciar(self):
        if not self.activo:
            self.activo = True
            self.hilo.start()
            print(f"[PC1-CONTROL] Receptor escuchando en tcp://*:{self.puerto}")

    def detener(self):
        self.activo = False
        try:
            self.socket_rep.close()
            self.contexto.term()
        except Exception:
            pass

    def buscar_interseccion(self, interseccion_id):
        """
        Espera intersecciones tipo:
        INT-A1, INT_B3, INT-C4, etc.
        """
        normalizada = interseccion_id.replace("_", "-").upper()

        if not normalizada.startswith("INT-"):
            return None

        resto = normalizada[4:]  # por ejemplo A1
        if len(resto) < 2:
            return None

        letra = resto[0]
        try:
            numero = int(resto[1:])
        except ValueError:
            return None

        return self.ciudad.obtener_interseccion(letra, numero)

    def aplicar_accion(self, interseccion_obj, accion, duracion):
        interseccion_id = f"INT_{interseccion_obj.M}{interseccion_obj.N}"

        if accion == "FORZAR_HORIZONTAL":
            print(
                f"[PC1-RECEPTOR] Aplicando prioridad horizontal en {interseccion_id} "
                f"por {duracion}s"
            )
            interseccion_obj.forzar_prioridad_horizontal(duracion)

        elif accion == "FORZAR_VERTICAL":
            print(
                f"[PC1-RECEPTOR] Aplicando prioridad vertical en {interseccion_id} "
                f"por {duracion}s"
            )
            interseccion_obj.forzar_prioridad_vertical(duracion)

        elif accion == "MANTENER_NORMAL":
            print(
                f"[PC1-RECEPTOR] Manteniendo operacion normal en {interseccion_id}"
            )

        elif accion == "RESTABLECER_NORMAL":
            print(
                f"[PC1-RECEPTOR] Restableciendo modo normal en {interseccion_id}"
            )
            # Por ahora se acepta, aunque el semaforo ya sale solo de prioridad.
        else:
            return False, "Accion no soportada"

        estado = interseccion_obj.semaforo.obtener_estado()
        sf = estado['semaforo_fila']
        sc = estado['semaforo_columna']

        print(
            f"[PC1-RECEPTOR] Estado semaforo -> "
            f"Interseccion={interseccion_id} | "
            f"{sf['semaforo_id']}={sf['estado']} | "
            f"{sc['semaforo_id']}={sc['estado']} | "
            f"Restan={estado['tiempo_restante']}s | "
            f"Prioridad={estado['modo_prioridad']} | "
            f"Direccion={estado['direccion_prioritaria']}"
        )

        return True, "Cambio aplicado correctamente"

    def procesar_comando(self, comando):
        interseccion_id = comando.get("interseccion")
        accion = comando.get("accion")
        duracion = comando.get("duracion", 15)

        if interseccion_id is None or accion is None:
            return {
                "ok": False,
                "mensaje": "Comando incompleto"
            }

        interseccion_obj = self.buscar_interseccion(interseccion_id)

        if interseccion_obj is None:
            return {
                "ok": False,
                "interseccion": interseccion_id,
                "mensaje": "Interseccion no encontrada"
            }

        ok, mensaje = self.aplicar_accion(interseccion_obj, accion, duracion)

        return {
            "ok": ok,
            "interseccion": interseccion_id,
            "accion_aplicada": accion,
            "mensaje": mensaje
        }

    def _run(self):
        while self.activo:
            try:
                mensaje = self.socket_rep.recv_string()
                comando = json.loads(mensaje)

                print(
                        f"[PC1-RECEPTOR] Comando recibido -> "
                        f"Interseccion={comando.get('interseccion')} | "
                        f"Accion={comando.get('accion')} | "
                        f"Duracion={comando.get('duracion')}"
                )       
                respuesta = self.procesar_comando(comando)

                self.socket_rep.send_string(json.dumps(respuesta))

            except Exception as e:
                try:
                    self.socket_rep.send_string(json.dumps({
                        "ok": False,
                        "mensaje": f"Error interno: {str(e)}"
                    }))
                except Exception:
                    pass