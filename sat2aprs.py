import re
import socket
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import time
import threading

app = Flask(__name__)

# APRS-IS login info
serverHost = 'theconnectdesk.com'
serverPort = 14580
aprsUser = 'CALLSIGN'  # Login call
aprsCall = None  # Default RF Call 
aprsPass = 'PASS'
text = 'Satellite Beacon'
symbol_chart = '\\'  # Replace with your desired symbol chart (e.g., '/', '\\', '!', etc.)
symbol = 'S'  # Replace with your desired symbol (e.g., 'S', 'O', 'P', etc.)


aprs_sock = None  # Define the socket outside the try-except block

def load_alias_map_from_file():
    alias_map = {}
    print("Opening File")
    with open('/root/app/map.txt', 'r') as file:
        print("File Opened")
        for line in file:
            parts = line.strip().split(',')
            if len(parts) == 2:
                phone_number, aprs_callsign = parts
                alias_map[phone_number] = aprs_callsign
    return alias_map
    
def update_alias_map_file(alias_map):
    map_file_path = '/root/app/map.txt'
    
    # Read the existing data from the file
    with open(map_file_path, 'r') as file:
        existing_data = file.readlines()
    
    # Update or add entries in the existing data
    updated_data = []
    for line in existing_data:
        parts = line.strip().split(',')
        if len(parts) == 2:
            phone_number, aprs_callsign = parts
            updated_call = alias_map.get(phone_number, aprs_callsign)
            updated_line = "{},{}\n".format(phone_number, updated_call)
            updated_data.append(updated_line)
    # Add new entries for numbers not already in the alias map
    for phone_number, aprs_callsign in alias_map.items():
        if not any(line.startswith(f"{phone_number},") for line in updated_data):
            updated_data.append("{},{}\n".format(phone_number, aprs_callsign))

    # Write the updated data back to the file
    with open(map_file_path, 'w') as file:
        file.writelines(updated_data)
    
    print("Wrote to file")
              

def connect_to_aprs_server():
    global aprs_sock
    while True:
        try:
            # Create and connect the APRS-IS socket
            aprs_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            aprs_sock.connect((serverHost, serverPort))
            login_str = 'user {} pass {} vers SatGate 0.1b\r\n'.format(aprsUser, aprsPass)
            aprs_sock.send(login_str.encode())
            response = aprs_sock.recv(1024).decode('utf-8')
            print('APRS-IS login response:', response)
            return
        except Exception as e:
            print('Error connecting to APRS-IS:', e)
            time.sleep(1)  # Wait for a while before attempting reconnection


# Function to send a keepalive APRS packet
def send_keepalive_packet():
    global aprs_sock  # Declare aprs_sock as global
    while True:
        if aprs_sock:
            keepalive_packet = '#\r\n'
            try:
                aprs_sock.send(keepalive_packet.encode())
                print("Keepalive Sent")
            except Exception as e:
                print("Error sending keepalive:", e)
                aprs_sock.close()
                aprs_sock = None  # Close and reset the socket
                connect_to_aprs_server()  # Attempt reconnection
        else:
            connect_to_aprs_server()  # If socket is not active, attempt reconnection
        time.sleep(30)
        
# Function to send a beacon APRS packet
def send_beacon_packet():
    global aprs_sock  # Declare aprs_sock as global
    while True:
        if aprs_sock:
            beacon_packet = 'SATGTE>NA7Q:!4610.49N\\12334.72WSMotorola Defy Satellite Gateway - NA7Q\r\n'
            try:
                aprs_sock.send(beacon_packet.encode())
                print("Beacon Sent")
            except Exception as e:
                print("Error sending beacon:", e)
                aprs_sock.close()
                aprs_sock = None  # Close and reset the socket
                connect_to_aprs_server()  # Attempt reconnection
        else:
            connect_to_aprs_server()  # If socket is not active, attempt reconnection
        time.sleep(600)


def latitude_to_ddmm(value):
    degrees = int(value)
    minutes_decimal = (value - degrees) * 60
    abs_minutes = abs(minutes_decimal)
    minutes = round(abs_minutes, 2)

    # Ensure that degrees and minutes have leading zeros
    degrees_str = "{:02d}".format(abs(degrees))
    minutes_str = "{:05.2f}".format(abs(minutes))

    # Ensure that the latitude always has at least 4 digits before the decimal point
    lat_ddmm = "{}{}".format(degrees_str, minutes_str)
    while len(lat_ddmm.split('.')[0]) < 4:
        lat_ddmm = "0" + lat_ddmm

    return lat_ddmm

def longitude_to_ddmm(value):
    degrees = int(value)
    minutes_decimal = (value - degrees) * 60
    abs_minutes = abs(minutes_decimal)
    minutes = round(abs_minutes, 2)

    # Ensure that degrees and minutes have leading zeros
    degrees_str = "{:03d}".format(abs(degrees))
    minutes_str = "{:05.2f}".format(abs(minutes))

    # Ensure that the longitude always has at least 5 digits before the decimal point
    lon_ddmm = "{}{}".format(degrees_str, minutes_str)
    while len(lon_ddmm.split('.')[0]) < 5:
        lon_ddmm = "0" + lon_ddmm

    return lon_ddmm

def send_aprs_packet(callsign, lat, lon, text):
    lat_ddmm = latitude_to_ddmm(lat)
    lon_ddmm = longitude_to_ddmm(lon)
    aprs_packet = '{}>APRS:!{}{}{}{}{}{}{}\r\n'.format(callsign, lat_ddmm, "N" if lat >= 0 else "S",symbol_chart, lon_ddmm, "E" if lon >= 0 else "W", symbol, text)


    try:
        aprs_sock.sendall(aprs_packet.encode())
        print('Sent APRS packet:', aprs_packet.strip())
    except Exception as e:
        print('Error sending APRS packet:', e)

@app.route('/sms', methods=['POST'])
def webhook():
    global aprsCall  # Declare aprsCall as a global variable

    incoming_sms = request.form.get('Body', '')
    latitude = None
    longitude = None
    comment = ""

    # Log incoming message
    print('Received Message:', incoming_sms)
    
    # Extract the sender's phone number from the Twilio request headers
    from_number_header = request.form.get('From', '').lstrip('+')
    
    # Load the alias map from the file
    alias_map = load_alias_map_from_file()    

    # Extract the phone number in the format "From: +15032985265"
    #from_number_match = re.search(r'From:\s*\+(\d+)', incoming_sms)
    #from_number = from_number_match.group(1).lstrip('+') if from_number_match else from_number_header
    #print('Sender\'s Phone Number:', from_number)
    
    from_number_match = re.search(r'From:\s*\+(\d+)', incoming_sms)
    from_number = from_number_match.group(1).lstrip('+') if from_number_match else from_number_header
    print('from_number_match:', from_number_match)
    print('from_number_header:', from_number_header)
    print('Final Sender\'s Phone Number:', from_number)
    


    # Look up the APRS callsign in the alias map based on the phone number
    aprsCall = alias_map.get(from_number, None)
    print('APRS Callsign for this number:', aprsCall)


    # Extract the APRS call sign following the "@" symbol (ignores double quotes)
    at_sign_match = re.search(r'@([^"]+)', incoming_sms)
    if at_sign_match:
        new_aprsCall = at_sign_match.group(1).strip().upper()  # Extract and convert aprsCall to uppercase
        print('Updated aprsCall:', new_aprsCall)

        # Update the alias map if the new aprsCall is not in it
        for number, call in alias_map.items():
            if call == aprsCall:
                alias_map[number] = new_aprsCall
                print('Updated alias map:', alias_map)
                
        # If the from_number is not in the alias map, add it with the new APRS call
        if from_number not in alias_map:
            alias_map[from_number] = new_aprsCall
            print('Added new entry to alias map:', alias_map)                
        
        # Set the new aprsCall
        aprsCall = new_aprsCall
        
        # Update the map file with the new data
        update_alias_map_file(alias_map)        

    if from_number:
        print('Found From Number:', from_number_header)

        # Process the message as needed
        # Example: Extract latitude, longitude, and comment from the message
        #lat_long_comment_match = re.search(r'(-?\d+\.\d+),(-?\d+\.\d+)\s*([^"]+)', incoming_sms)
        lat_long_comment_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*([^"]+)', incoming_sms)


        if lat_long_comment_match:
            latitude = float(lat_long_comment_match.group(1))
            longitude = float(lat_long_comment_match.group(2))
            comment = lat_long_comment_match.group(3).strip()

            # If the comment is "undefined," use the default comment 'text'
            if comment.lower() == "undefined":
                comment = text

            print('Detected Lat Long: ({}, {})'.format(latitude, longitude))
            print('Detected Comment:', comment)

            # Convert latitude and longitude to DDMM.MM format without dashes
            lat_ddmm = latitude_to_ddmm(latitude)
            long_ddmm = longitude_to_ddmm(longitude)

            print('Converted Lat Long to DDMM.MM: {}, {}'.format(lat_ddmm, long_ddmm))
            print('{}/{}'.format(lat_ddmm, long_ddmm))
            print('APRS Comment:', comment)

            # Send APRS packet using the mapped callsign 'aprsCall' only if it's found in the alias map
            if aprsCall in alias_map.values():
                send_aprs_packet(aprsCall, latitude, longitude, comment)
            else:
                print("APRS Callsign not found in alias map. Skipping APRS packet.")

        else:
            print('No Lat Long and Comment detected.')

    else:
        print('No From Number detected.')

    response = MessagingResponse()
    return str(response)


if __name__ == '__main__':
    connect_to_aprs_server()  # Initial connection


    # Start a thread to send keepalive packets
    print("Start thread for keepalive")
    keepalive_thread = threading.Thread(target=send_keepalive_packet)
    keepalive_thread.daemon = True
    keepalive_thread.start()

    # Start a thread to send beacon packets
    print("Start thread for beacons")
    beacon_thread = threading.Thread(target=send_beacon_packet)
    beacon_thread.daemon = True
    beacon_thread.start()

    print("run host")
    app.run(host='0.0.0.0', port=5000, debug=False)
