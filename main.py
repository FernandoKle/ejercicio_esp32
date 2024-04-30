# red LED: ON == WiFi fail
# green LED heartbeat: demonstrates scheduler is running.

from mqtt_as import MQTTClient
from mqtt_local import config
import uasyncio as asyncio
import dht, machine
import btree
import json
import ubinascii
from machine import Timer, Pin
from settings import *

# Base de datos key/value con un btree
try:
    f = open("mydb", "r+b")
    nuevo_db = False
except OSError:
    f = open("mydb", "w+b")
    nuevo_db = True
    
db = btree.open(f)


d = dht.DHT22(machine.Pin(25)) # 25 en el simulador !
rele = Pin(4, Pin.OUT)
led = Pin(2, Pin.OUT)

topic_base = ubinascii.hexlify(machine.unique_id()).decode('utf-8')

class Datos():
    modo_auto = 1 #True
    periodo = 3
    setpoint = 26
    rele_estado = 0 #False
    humedad = 0
    temperatura = 0

global datos
datos = Datos()

# DEBUG
nuevo_db = True

##################### Variables #####################
if nuevo_db:
    datos.modo_auto = 1 #True
    datos.periodo = 3
    datos.setpoint = 26
    datos.rele_estado = 0 #False
    db["modo"] = str(datos.modo_auto) 
    db["periodo"] = str(datos.periodo) 
    db["rele"] = str(datos.rele_estado)
    db["setpoint"] = str(datos.setpoint) 
else:
    datos.modo_auto = int(db["modo"])
    datos.periodo = int(db["periodo"])
    datos.rele_estado = int(db["rele"])
    datos.setpoint = int(db["setpoint"])

db.close()
f.close()

#####################################################

async def wifi_han(state):
    print('Wifi is ', 'up' if state else 'down')
    await asyncio.sleep(1)

# If you connect with clean_session True, must re-subscribe (MQTT spec 3.1.2.4)
async def conn_han(client):
    await client.subscribe('destello/' + topic_base, 1)
    await client.subscribe('rele/' + topic_base, 1)
    await client.subscribe('setpoint/' + topic_base, 1)
    await client.subscribe('periodo/' + topic_base, 1)
    await client.subscribe('modo/' + topic_base, 1)
    
##############################################################

async def destello():
    print('ESP32 usa Destello !')
    led.value(True)
    await asyncio.sleep(300)
    led.value(False)
    await asyncio.sleep(300)
    led.value(True)
    await asyncio.sleep(300)
    led.value(False)
    print('Fue muy efectivo !')

##############################################################

def recepcion(topic, msg, retained):
    global datos

    msg = msg.decode()
    topic = topic.decode()

    print("Msg:", msg)
    print("Topic:", topic)

    if 'setpoint' in topic:
        datos.setpoint = int(msg)
        print('setpoint =', datos.setpoint)
        
    if 'destello' in topic:
        await destello()

    if 'periodo' in topic:
        datos.periodo = int(msg)
        print('periodo =', datos.periodo)
        
    if 'rele' in topic and datos.modo_auto == False:
        if 'true' in msg.lower() or int(msg) == 1:
            datos.rele_estado = 1
        else:
            datos.rele_estado = 0
        
    if 'modo' in topic:
        if 'auto' in msg.lower():
            datos.modo_auto = 1
            print('modo automatico !')
        else:
            datos.modo_auto = 0
            print('modo MANUAL')
        
##############################################################

async def muestreo_rele():
    global datos

    while True:
        print("Muestreo del rele...")
        if datos.modo_auto:
            if datos.temperatura >= datos.setpoint:
                datos.rele_estado = 1
            else:
                datos.rele_estado = 0

        rele.value(datos.rele_estado)
        print(f'Rele = {datos.rele_estado}')

        await asyncio.sleep(datos.periodo)

##############################################################

async def transmitir(client):
    global datos

    while True:

        mensaje = json.dumps({'temperatura': datos.temperatura,
                            'humedad': datos.humedad,
                            'periodo': datos.periodo,
                            'modo_automatico': datos.modo_auto,
                            'setpoint':datos.setpoint})

        print('Enviando Datos')
        await client.publish('iot2024/' + topic_base, mensaje, qos = 1)

        await asyncio.sleep(5)

##############################################################

async def medir():
    global datos

    while True:
        print("Midiendo temperatura/humedad...")
        try:
            d.measure()
            try:
                datos.temperatura = d.temperature()
            except OSError as e:
                print("sin sensor temperatura")
            try:
                datos.humedad = d.humidity()
            except OSError as e:
                print("sin sensor humedad")
        except OSError as e:
            print("sin sensor")
        
        await asyncio.sleep(3)

##############################################################

async def actualizar_db():
    global datos

    while True:
        print("Actualizando base de datos...")
        f = open("mydb", "w+b")
        db = btree.open(f)
        db["modo"] = str(datos.modo_auto)
        db["periodo"] = str(datos.periodo)
        db["rele"] = str(datos.rele_estado)
        db["setpoint"] = str(datos.setpoint)
        db.close()
        f.close()
        await asyncio.sleep(10)

########################### MAIN #############################

async def main(client):

    print("topico:", 'iot2024/' + topic_base + '/#')
    
    print('Intentando conectar al wi-fi:', SSID)
    print('con la contrasena:', password)

    await client.connect()
    #client.connect()
    n = 0
    await asyncio.sleep(2)  # Give broker time
    
    await client.publish('iot2024/' + topic_base, "Iniciando...", qos = 1)

    tasks = []

    tasks.append( asyncio.create_task( medir()              ))
    tasks.append( asyncio.create_task( muestreo_rele()      )) 
    tasks.append( asyncio.create_task( transmitir(client)   )) 
    tasks.append( asyncio.create_task( actualizar_db()      )) 

    try:
        res = await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.TimeoutError:    
        print('Timeout')            
    except asyncio.CancelledError:
        print('Cancelled')

######################### END MAIN ###########################

# Define configuration
config['subs_cb'] = recepcion
config['connect_coro'] = conn_han
config['wifi_coro'] = wifi_han
config['ssl'] = True
config['ssid'] = SSID
config['wifi_pw'] = password

# Set up client
MQTTClient.DEBUG = False  # Optional
client = MQTTClient(config)

# Run
try:
    asyncio.run(main(client))
finally:
    client.close()
    asyncio.new_event_loop()

# Guardar y terminar
f = open("mydb", "w+b")
db = btree.open(f)
db["modo"] = str(datos.modo_auto)
db["periodo"] = str(datos.periodo)
db["rele"] = str(datos.rele_estado)
db["setpoint"] = str(datos.setpoint)
db.close()
f.close()
