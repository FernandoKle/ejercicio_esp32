# red LED: ON == WiFi fail
# green LED heartbeat: demonstrates scheduler is running.

from mqtt_as import MQTTClient
from mqtt_local import config
import uasyncio as asyncio
import dht, machine
import btree

# Base de datos key/value con un btree
try:
    f = open("mydb", "r+b")
    nuevo_db = False
except OSError:
    f = open("mydb", "w+b")
    nuevo_db = True
    
db = btree.open(f)


d = dht.DHT22(machine.Pin(13))
rele = Pin(2, Pin.OUT)
led = Pin(2, Pin.OUT)

topic_base = machine.unique_id()

##################### Variables #####################
if nuevo_db:
    modo_auto = True
    periodo = 1
    setpoint = 26
    rele_estado = False
else:
    modo_auto = db[b"modo"]
    periodo = db[b"periodo"]
    rele_estado = db[b"rele"]
    setpoint = db[b"setpoint"]
#####################################################

def sub_cb(topic, msg, retained):
    print('Topic = {} -> Valor = {}'.format(topic.decode(), msg.decode()))

async def wifi_han(state):
    print('Wifi is ', 'up' if state else 'down')
    await asyncio.sleep(1)

# If you connect with clean_session True, must re-subscribe (MQTT spec 3.1.2.4)
async def conn_han(client):
    await client.subscribe('temperatura/' + topic_base, 1)
    await client.subscribe('humedad/' + topic_base, 1)
    await client.subscribe('setpoint/' + topic_base, 1)
    await client.subscribe('periodo/' + topic_base, 1)
    await client.subscribe('modo/' + topic_base, 1)

########################## MAIN ###########################

async def main(client):
    await client.connect()
    n = 0
    await asyncio.sleep(2)  # Give broker time

    while True:
        try:
            d.measure()

            try:
                temperatura = d.temperature()
                
                if modo_auto:
                    if temperatura >= setpoint:
                        rele_estado = True
                    else:
                        rele_estado = False

                #await client.publish('fernando/temperatura', '{}'.format(temperatura), qos = 1)
            except OSError as e:
                print("sin sensor temperatura")
            try:
                humedad = d.humidity()

                #await client.publish('fernando/humedad', '{}'.format(humedad), qos = 1)
            except OSError as e:
                print("sin sensor humedad")
        except OSError as e:
            print("sin sensor")
            
        rele.value(rele_estado)
        db[b"rele"] = rele_estado

        await asyncio.sleep(20)  # Broker is slow

#################### END MAIN ########################

# Define configuration
config['subs_cb'] = sub_cb
config['connect_coro'] = conn_han
config['wifi_coro'] = wifi_han
config['ssl'] = True

# Set up client
MQTTClient.DEBUG = True  # Optional
client = MQTTClient(config)

try:
    asyncio.run(main(client))
finally:
    client.close()
    asyncio.new_event_loop()

db.close()
f.close()