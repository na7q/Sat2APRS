# Sat2APRS
Motorola Defy Satellite Tracking to APRS

This uses the Twilio SMS API Services for receiving the "check in" GPS coordinates sent from the Bullitt application. The script processes the message and retrieves the Lat/Long from the SMS Message. It is then formatted into a perfectly crafted APRS packet that is sent to the APRS-IS of your choice. It uses a simple webhook to receive the SMS from Twilio.
