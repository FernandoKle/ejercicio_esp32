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

global modo_auto, periodo, setpoint, rele_estado

# DEBUG
nuevo_db = True

##################### Variables #####################
if nuevo_db:
    modo_auto = 1 #True
    periodo = 3
    setpoint = 26
    rele_estado = 0 #False
    db["modo"] = str(modo_auto) 
    db["periodo"] = str(periodo) 
    db["rele"] = str(rele_estado)
    db["setpoint"] = str(setpoint) 
else:
    modo_auto = int(db["modo"])
    periodo = int(db["periodo"])
    rele_estado = int(db["rele"])
    setpoint = int(db["setpoint"])

temperatura = 0
humedad = 0

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
    
datos = ""

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
    global modo_auto, periodo, setpoint, rele_estado

    msg = msg.decode()
    topic = topic.decode()

    if 'setpoint' in topic:
        setpoint = int(msg)
        print('setpoint =', setpoint)
        
    if 'destello' in topic:
        await destello()

    if 'periodo' in topic:
        periodo = int(msg)
        print('periodo =', periodo)
        publicar.init(period=periodo, mode=Timer.PERIODIC, 
            callback=lambda t: interrupcion_periodica() )
        
    if 'rele' in topic and modo_auto == False:
        if 'true' in msg.lower() or int(msg) == 1:
            rele_estado = 1
        else:
            rele_estado = 0
        
    if 'modo' in topic:
        if 'auto' in msg.lower():
            modo_auto = 1
            print('modo automatico !')
        else:
            modo_auto = 0
            print('modo MANUAL')
        
##############################################################

async def muestreo_rele():
    global periodo, modo_auto, temperatura, humedad, setpoint, rele_estado, rele

    while True:
        print("Muestreo del rele...")
        if modo_auto:
            if temperatura >= setpoint:
                rele_estado = 1
            else:
                rele_estado = 0

        rele.value(rele_estado)
        print(f'Rele = {rele_estado}')

        await asyncio.sleep(periodo)

##############################################################

async def transmitir(client):
    global modo_auto, periodo, setpoint, temperatura, humedad

    while True:

        datos = json.dumps({'temperatura': temperatura,
                            'humedad': humedad,
                            'periodo': periodo,
                            'modo_automatico': modo_auto,
                            'setpoint':setpoint})

        print('Enviando Datos')
        await client.publish('iot2024/' + topic_base, datos, qos = 1)

        await asyncio.sleep(5)

##############################################################

async def medir():
    global modo_auto, periodo, setpoint, temperatura, humedad

    while True:
        print("Midiendo temperatura/humedad...")
        try:
            d.measure()
            try:
                temperatura = d.temperature()
            except OSError as e:
                print("sin sensor temperatura")
            try:
                humedad = d.humidity()
            except OSError as e:
                print("sin sensor humedad")
        except OSError as e:
            print("sin sensor")
        
        await asyncio.sleep(3)

##############################################################

async def actualizar_db():
    while True:
        print("Actualizando base de datos...")
        f = open("mydb", "r+b")
        db = btree.open(f)
        db["modo"] = str(modo_auto)
        db["periodo"] = str(periodo)
        db["rele"] = str(rele_estado)
        db["setpoint"] = str(setpoint)
        db.close()
        f.close()
        await asyncio.sleep(10)

########################### MAIN #############################

async def main(client):
    global modo_auto, periodo, setpoint, rele_estado, temperatura, humedad

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
        res = await asyncio.gather(*tasks, return_exceptions=False)
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
f = open("mydb", "r+b")
db = btree.open(f)
db["modo"] = str(modo_auto)
db["periodo"] = str(periodo)
db["rele"] = str(rele_estado)
db["setpoint"] = str(setpoint)
db.close()
f.close()
