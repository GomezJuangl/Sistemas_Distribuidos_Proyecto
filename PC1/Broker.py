import zmq
import threading

class Broker:
    def __init__(self):
        self.context = zmq.Context()

        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.bind("tcp://*:5555")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind("tcp://*:5556")

        #self.push_socket = self.context.socket(zmq.PUSH)
        #self.push_socket.bind("tcp://*:5556")




        #____________________________________________________________
        #self.push_socket1 = self.context.socket(zmq.PUSH)
        #self.push_socket.bind("tcp://*:6000")

        #self.push_socket2 = self.context.socket(zmq.PUSH)
        #self.push_socket2.bind("tcp://*:5559")
        #____________________________________________________________

    #def enviar(self,socket,mensaje, nombre):
        #try:
         #   socket.send_string(mensaje,zmq.NOBLOCK)
        #except zmq.Again:
         #   print(f"⚠️ Servicio {nombre} no disponible")

    def run(self):
        while True:
            #self.pub_socket.send_string(mensaje)  
            #          
            mensaje = self.sub_socket.recv_string()
            self.pub_socket.send_string(mensaje) 
            #self.push_socket.send_string(mensaje)


            #threading.Thread(target=self.enviar, args=(self.push_socket1, mensaje, "BD principal")).start()
            #threading.Thread(target=self.enviar, args=(self.push_socket2, mensaje, "BD réplica")).start()
            print("📤 Recibido y Enviado:", mensaje[:60])
            #except zmq.Again:
            #print("⚠️ BD no disponible, mensaje descartado")

if __name__ == "__main__":
    broker = Broker()
    broker.run()