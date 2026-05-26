# Gestión Inteligente de Tráfico Urbano (GITU)

Sistema distribuido para monitoreo, análisis y control de tráfico urbano usando ZeroMQ.

## Arquitectura

| Máquina | IP | Componentes |
|---------|------|-------------|
| PC1 | 10.43.99.110 | Sensores, Broker ZMQ, Receptor Control Semáforos, Generador de Carga |
| PC2 | 10.43.99.102 | Servicio Analítica, Servicio Control Semáforos, BD Réplica, Scripts de Medición |
| PC3 | 10.43.100.49 | BD Principal, Monitoreo y Consulta, Disparador VD2 |

## Requisitos

En las 3 máquinas:
```bash
sudo apt install python3 python3-pip iperf3 -y
pip3 install pyzmq pandas matplotlib psutil
```

## Puertos ZMQ

| Puerto | Patrón | Dirección |
|--------|--------|-----------|
| 5555 | PUB/SUB | Sensores → Broker |
| 5556 | PUB/SUB | Broker → Analítica |
| 5101 | REQ/REP | Monitoreo → BD Principal |
| 5102 | REQ/REP | Monitoreo → BD Réplica (fallback) |
| 6001 | REQ/REP | Monitoreo → Analítica (comandos de prioridad) |
| 6002 | PUSH/PULL | Analítica → Control Semáforos |
| 6003 | REQ/REP | Control Semáforos → Receptor PC1 |
| 6004 | REQ/REP | Medir Rendimiento → Disparador VD2 |
| 6010 | REQ/REP | Prueba Estrés (PC2) → Generador Controlable (PC1) |
| 7001 | PUSH/PULL | Analítica → BD Principal |
| 7002 | PUSH/PULL | Analítica → BD Réplica |
| 7003 | REQ/REP | Analítica health-check → BD Principal |
| 7004 | PUSH/PULL | Analítica sync → BD Principal (recuperación) |

## Ejecución del sistema (3 PCs)

### PC1
```bash
cd ~/Downloads/PC1/Broker && python3 Broker.py
cd ~/Downloads/PC1 && python3 main.py
```

### PC2
```bash
cd ~/Downloads/PC2/BaseDatosReplica && python3 BaseDatos_Replica.py
cd ~/Downloads/PC2 && python3 servicio_control_semaforos.py
cd ~/Downloads/PC2 && python3 servicio_analitica.py
```

### PC3
```bash
cd ~/Downloads/PC3/BaseDatosPrincipal && python3 BaseDatos.py
cd ~/Downloads/PC3 && python3 Monitoreo_Consulta.py
```

## Prueba de tolerancia a fallos

Para probar la caída y recuperación de la BD Principal:

1. Levantar todo el sistema normalmente
2. Dejar correr X minutos para que se acumulen datos
3. Matar BD Principal: Ctrl+C en `BaseDatos.py` (PC3)
4. Esperar 1-2 minutos (analítica detecta la caída y sigue guardando solo en réplica)
5. Volver a levantar: `cd ~/Downloads/PC3/BaseDatosPrincipal && python3 BaseDatos.py`
6. Analítica sincroniza automáticamente los datos faltantes desde la réplica

## Pruebas de rendimiento

### Métricas

- **Throughput**: Cantidad de solicitudes almacenadas en la BD réplica en una ventana de 2 minutos
- **Latencia de comando de prioridad**: Tiempo del flujo completo desde que se envía un comando de prioridad (ambulancia) en PC3 hasta que el semáforo cambia en PC1

### Generador de carga

El generador (`PC1/generador_carga.py`) inyecta mensajes ZMQ al broker a una tasa configurable para estresar el sistema.

```bash
cd ~/Downloads/PC1
python3 generador_carga.py --tasa 1000 --duracion 900
```

### Broker Multihilo y el GIL de Python

El broker multihilo (`PC1/Broker/Broker_multihilo.py`) permite configurar el número de workers con la variable de entorno `BROKER_WORKERS`:

```bash
BROKER_WORKERS=8 python3 Broker_multihilo.py
```

Python tiene el GIL (Global Interpreter Lock) que solo permite que un hilo ejecute código Python a la vez. Para lograr paralelismo real entre workers, el broker incluye una capa de auditoría con escrituras SQLite por cada mensaje. Las operaciones de I/O a disco liberan el GIL, permitiendo que mientras un worker escribe en disco, otros procesen mensajes simultáneamente.

### Ejecución de pruebas en 3 PCs

#### Scripts por máquina

| PC | Scripts |
|----|---------|
| PC1 | `pc1_servicios.sh`, `pc1_solo_vd2.sh`, `pc1_iperf_servers.sh`, `pc1_estres.sh` |
| PC2 | `pc2_caso.sh`, `pc2_solo_vd2.sh`, `pc2_iperf_ronda.sh`, `pc2_estres.sh` |
| PC3 | `pc3_servicios.sh`, `pc3_iperf_servers.sh` |

Dar permisos antes de usar: `chmod 777 *.sh`

#### Ronda 1 — Prueba de throughput + latencia base (sin iperf3)

Se mide la cantidad de solicitudes almacenadas en la BD en 2 minutos y el tiempo de respuesta del comando de prioridad, variando el número de hilos del broker.

Para cada caso, ejecutar en orden:
```
PC3:  ./pc3_servicios.sh
PC1:  ./pc1_servicios.sh <hilos> <escenario>
PC2:  ./pc2_caso.sh <escenario> <diseno>
```

Cuando PC2 termina y aparece el prompt, hacer Ctrl+C en PC1 y PC3.

Ejemplo: Escenario A, 4 hilos:
```
PC3:  ./pc3_servicios.sh
PC1:  ./pc1_servicios.sh 4 A
PC2:  ./pc2_caso.sh A multihilo_4
```

Para el diseño original (1 hilo): `./pc1_servicios.sh 1 A` y `./pc2_caso.sh A original`

#### Ronda 2 — Prueba de latencia con red congestionada (iperf3, solo tiempo de respuesta)

Se mide únicamente el tiempo de respuesta del comando de prioridad con la red congestionada mediante iperf3, para comparar contra los tiempos sin congestión.

Primero levantar servidores iperf3 (una vez, se dejan corriendo toda la ronda):
```
PC1:  ./pc1_iperf_servers.sh
PC3:  ./pc3_iperf_servers.sh
```

Para cada caso:
```
PC3:  ./pc3_servicios.sh
PC1:  ./pc1_solo_vd2.sh <hilos> <escenario>
PC2:  ./pc2_iperf_ronda.sh <escenario> <diseno>
```

Al terminar todos los casos:
```
PC1:  ./pc1_iperf_servers.sh stop
PC3:  ./pc3_iperf_servers.sh stop
```

Se usan 16 procesos iperf3 TCP simultáneos (8 hacia PC1 + 8 hacia PC3) para saturar la red de 10Gbps.

#### Ronda 3 — Prueba de estrés (carga máxima del sistema)

Se determina la carga máxima que el sistema puede procesar sin perder mensajes. Se fija el broker en 8 hilos (punto óptimo encontrado en la Ronda 1) y se incrementa progresivamente la tasa de inyección del generador de carga (50, 100, 200, 500, 1000, 2000, 5000 msg/s). Para cada tasa se mide durante 60 segundos el throughput real (registros almacenados en BD), el uso de CPU de analítica y la tasa de pérdida de mensajes.

El generador controlable (`PC1/generador_carga_estres.py`) se queda escuchando en el puerto 6010 y recibe comandos remotos desde PC2 para iniciar, parar y cambiar la tasa de inyección entre rondas sin intervención manual.

Ejecutar en orden:
```
PC3:  ./pc3_servicios.sh
PC1:  ./pc1_estres.sh
PC2:  ./pc2_estres.sh
```

Cuando PC2 termina y muestra "PRUEBA DE ESTRÉS COMPLETADA", hacer Ctrl+C en PC1 y PC3.

Para ejecutar con tasas o ventana personalizadas:
```
PC2:  ./pc2_estres.sh "50,100,500,1000" 90
```

Tiempo estimado con las tasas por defecto (7 tasas, ventana 60s): ~9 minutos.

#### Generar gráficas

```bash
cd ~/Downloads/PC2/Pruebas
python3 generar_graficas.py
```

La gráfica de la prueba de estrés se genera automáticamente al finalizar `pc2_estres.sh`

Las gráficas se guardan en `PC2/Pruebas/graficas/`.

### Gráficas generadas

| Archivo | Descripción |
|---------|-------------|
| `curva_inflexion_vd1.png` | Curva de inflexión: solicitudes almacenadas en BD vs número de hilos del broker |
| `vd2_red_A.png` | Tiempo de respuesta del comando de prioridad sin iperf3 vs con iperf3 (Escenario A) |
| `vd2_red_B.png` | Tiempo de respuesta del comando de prioridad sin iperf3 vs con iperf3 (Escenario B) |
| `solicitudes_por_escenario.png` | Barras de solicitudes almacenadas por escenario y diseño |
| `latencia_por_escenario.png` | Barras de latencia por escenario y diseño |
| `estres_carga_maxima.png` | Carga máxima del sistema: throughput real y tasa de pérdida vs tasa de inyección |

## Configuración de la ciudad

- Matriz: 4x4 (intersecciones A1 a D4)
- Semáforos: ciclo de 15 segundos por fase
- Sensores: Cámara cada 2s, GPS cada 3s, Espira cada 30s
- Zona de alta demanda: INT_B3

## Integrantes

- Juan Guillermo Gómez Landinez
- Xamuel Pérez Madrigal