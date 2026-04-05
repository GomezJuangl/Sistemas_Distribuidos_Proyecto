# Gestion Inteligente de Trafico Urbano

Sistema distribuido para monitoreo, analisis y control de trafico urbano usando ZeroMQ.

## Arquitectura

| Maquina | IP | Componentes |
|---------|------|-------------|
| PC1 | 10.43.99.110 | Sensores, Broker ZMQ, Receptor Control Semaforos |
| PC2 | 10.43.99.102 | Servicio Analitica, Servicio Control Semaforos, BD Replica |
| PC3 | 10.43.100.49 | BD Principal, Monitoreo y Consulta |

## Requisitos

```
pip install pyzmq
```

## Orden de ejecucion

### 1. PC1 - Broker
```
cd PC1/Broker
python3 Broker.py
```

### 2. PC3 - Base de datos principal
```
cd PC3/BaseDatosPrincipal
python3 BaseDatos.py
```

### 3. PC2 - Base de datos replica
```
cd PC2/BaseDatosReplica
python3 BaseDatos_Replica.py
```

### 4. PC2 - Servicio de control de semaforos
```
cd PC2
python3 servicio_control_semaforos.py
```

### 5. PC2 - Servicio de analitica
```
cd PC2
python3 servicio_analitica.py
```

### 6. PC1 - Ciudad y sensores
```
cd PC1
python3 main.py
```

### 7. PC3 - Monitoreo y consulta
```
cd PC3
python3 Monitoreo_Consulta.py
```

## Patrones ZeroMQ utilizados

- PUB/SUB: Sensores -> Broker -> Analitica
- PUSH/PULL: Analitica -> BD Principal, Analitica -> BD Replica, Analitica -> Control Semaforos
- REQ/REP: Monitoreo <-> Analitica, Monitoreo <-> BD Principal, Control Semaforos <-> Receptor PC1

## Configuracion de la ciudad

- Matriz: 4x4 (intersecciones A1 a D4)
- Semaforos: ciclo de 15 segundos por fase
- Sensores: Camara cada 2s, GPS cada 3s, Espira cada 30s
- Zona de alta demanda: INT_B3

## Integrantes

- Miguel Angel Garcia Rodriguez
- Juan Guillermo Gomez Landinez
- Xamuel Perez Madrigal
