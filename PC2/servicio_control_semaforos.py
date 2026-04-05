import json
from datetime import datetime
import zmq


class ServicioControlSemaforos:
    def __init__(self):
        # ==========================================
        # CONFIGURACION
        # ==========================================
        self.PULL_IP = "127.0.0.1"
        self.PULL_PUERTO = 6002

        self.PC1_IP = "10.43.99.110"
        self.PC1_PUERTO = 6003

        # ==========================================
        # ZMQ
        # ==========================================
        self.contexto = zmq.Context()

        self.socket_pull_analitica = None
        self.socket_req_pc1 = None

    def conectar_servicios(self):
        # Recibe desde analitica
        self.socket_pull_analitica = self.contexto.socket(zmq.PULL)
        self.socket_pull_analitica.bind(f"tcp://*:{self.PULL_PUERTO}")

        # Envia hacia PC1
        self.socket_req_pc1 = self.contexto.socket(zmq.REQ)
        self.socket_req_pc1.connect(f"tcp://{self.PC1_IP}:{self.PC1_PUERTO}")

        print(f"[CONTROL] Escuchando de analitica en tcp://*:{self.PULL_PUERTO}")
        print(f"[CONTROL] Conectado a PC1 en tcp://{self.PC1_IP}:{self.PC1_PUERTO}")

    def parsear_comando(self, mensaje):
        try:
            comando = json.loads(mensaje)

            if "interseccion" not in comando or "accion" not in comando:
                print("[CONTROL] Comando incompleto:", comando)
                return None

            return comando

        except json.JSONDecodeError:
            print("[CONTROL] Error parseando comando:", mensaje)
            return None

    def validar_accion(self, accion):
        acciones_validas = {
            "MANTENER_NORMAL",
            "FORZAR_HORIZONTAL",
            "FORZAR_VERTICAL",
            "RESTABLECER_NORMAL",
        }
        return accion in acciones_validas

    def reenviar_a_pc1(self, comando):
        try:
            self.socket_req_pc1.send_string(json.dumps(comando))
            respuesta = self.socket_req_pc1.recv_string()
            return json.loads(respuesta)
        except Exception as e:
            return {
                "ok": False,
                "mensaje": f"Error comunicando con PC1: {str(e)}"
            }

    def procesar_comando(self, comando):
        interseccion = comando["interseccion"]
        accion = comando["accion"]
        duracion = comando.get("duracion", 15)

        if not self.validar_accion(accion):
            print(f"[CONTROL] Accion invalida: {accion}")
            return

        payload_pc1 = {
            "interseccion": interseccion,
            "accion": accion,
            "duracion": duracion,
            "timestamp": datetime.now().isoformat(),
            "origen": "servicio_control_semaforos"
        }

        print(
            f"[CONTROL] Reenviando a PC1 -> "
            f"Interseccion={interseccion} | Accion={accion} | Duracion={duracion}"
        )

        respuesta = self.reenviar_a_pc1(payload_pc1)
        print(f"[CONTROL] Respuesta PC1: {respuesta}")

    def recibir_comandos(self):
        while True:
            mensaje = self.socket_pull_analitica.recv_string()
            comando = self.parsear_comando(mensaje)

            if comando is None:
                continue

            self.procesar_comando(comando)

    def cerrar(self):
        if self.socket_pull_analitica is not None:
            self.socket_pull_analitica.close()

        if self.socket_req_pc1 is not None:
            self.socket_req_pc1.close()

        self.contexto.term()

    def ejecutar(self):
        try:
            self.conectar_servicios()
            self.recibir_comandos()
        except KeyboardInterrupt:
            print("\n[CONTROL] Servicio detenido por el usuario")
        finally:
            self.cerrar()


def main():
    servicio = ServicioControlSemaforos()
    servicio.ejecutar()


if __name__ == "__main__":
    main()