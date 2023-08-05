import re
import socket
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

def decimal_to_ddmm(value):
    degrees = int(value)
    minutes_decimal = (value - degrees) * 60
    abs_minutes = abs(minutes_decimal)
    minutes = round(abs_minutes, 2)
    return "{:02d}{:05.2f}".format(abs(degrees), abs(minutes))

# APRS-IS login info
serverHost = 'rotate.aprs2.net'
serverPort = 14580
aprsUser = 'CALL'
aprsPass = 'PASS'
text = 'Sat2APRS'

# Create and connect the APRS-IS socket
aprs_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    aprs_sock.connect((serverHost, serverPort))
    login_str = 'user {} pass {} vers Sat2APRS 0.1b\r\n'.format(aprsUser, aprsPass)
    aprs_sock.send(login_str.encode())
    response = aprs_sock.recv(1024).decode('utf-8')
    print('APRS-IS login response:', response)
except Exception as e:
    print('Error connecting to APRS-IS:', e)

def send_aprs_packet(callsign, lat, lon, text):
    lat_ddmm = decimal_to_ddmm(lat)
    lon_ddmm = decimal_to_ddmm(lon)
    aprs_packet = '{}>APRS:!{}{}\{}{}S{}\r\n'.format(callsign, lat_ddmm, "N" if lat >= 0 else "S", lon_ddmm, "E" if lon >= 0 else "W", text)

    try:
        aprs_sock.sendall(aprs_packet.encode())
        print('Sent APRS packet:', aprs_packet.strip())
    except Exception as e:
        print('Error sending APRS packet:', e)


@app.route('/sms', methods=['POST'])
def webhook():
    incoming_sms = request.form.get('Body', '')
    latitude = None
    longitude = None
    comment = ""

    # Log incoming message
    print('Received Message:', incoming_sms)

    # Search for latitude, longitude, and comment in the message using regular expressions
    lat_long_comment_match = re.search(r'(-?\d+\.\d+),(-?\d+\.\d+)\s*([^.\"\n]+)', incoming_sms)

    if lat_long_comment_match:
        latitude = float(lat_long_comment_match.group(1))
        longitude = float(lat_long_comment_match.group(2))
        comment = lat_long_comment_match.group(3).strip()

        # If the comment is "undefined", use the default comment 'text'
        if comment.lower() == "undefined":
            comment = text

        print('Detected Lat Long: ({}, {})'.format(latitude, longitude))
        print('Detected Comment:', comment)

        # Convert latitude and longitude to DDMM.MM format without dashes
        lat_ddmm = decimal_to_ddmm(latitude)
        long_ddmm = decimal_to_ddmm(longitude)

        print('Converted Lat Long to DDMM.MM: {}, {}'.format(lat_ddmm, long_ddmm))
        print('{}/{}'.format(lat_ddmm, long_ddmm))
        print('APRS Comment:', comment)

        # Send APRS packet
        send_aprs_packet(aprsUser, latitude, longitude, comment)

    else:
        print('No Lat Long and Comment detected.')

    response = MessagingResponse()
    return str(response)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
