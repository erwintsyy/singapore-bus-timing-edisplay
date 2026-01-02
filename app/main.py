import sys
import os
import textwrap
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setting up directories
picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

import requests
import json
from datetime import datetime
from waveshare_epd import epd7in5h
import time
from PIL import Image, ImageDraw, ImageFont
import traceback
import logging


logging.basicConfig(level=logging.DEBUG)

START_HOUR = 7
END_HOUR = 9
on_break_displayed = False

def get_weather_information():
    url = "https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook"
    headers = {"X-Api-Key": "YOUR_SECRET_TOKEN"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        weather_data = response.json()   # <-- your actual weather data
        return weather_data
    else:
        print("Error:", response.status_code, response.text)
        return None

def get_bus_arrival(api_key, bus_stop_code):
    url = "https://datamall2.mytransport.sg/ltaodataservice/v3/BusArrival?BusStopCode=" + bus_stop_code
    headers = {
        'AccountKey': api_key,
        'accept': 'application/json'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        services = data.get("Services", [])
        bus_info = []

        for service in services:
            service_no = service["ServiceNo"]
            arrival_times = []
            for bus in ["NextBus", "NextBus2", "NextBus3"]:
                if service.get(bus):
                    eta = service[bus]["EstimatedArrival"]
                    flag = service[bus]["Load"]
                    if eta:
                        eta_time = datetime.strptime(eta, "%Y-%m-%dT%H:%M:%S%z")
                        time_diff = (eta_time - datetime.now(eta_time.tzinfo)).total_seconds() / 60
                        if time_diff < 0:
                            arrival_times.append(["Left", flag])
                        elif time_diff < 1:
                            arrival_times.append(["Arr", flag])
                        else:
                            arrival_times.append([round(time_diff), flag])
            if arrival_times:
                bus_info.append((service_no, arrival_times))
        return bus_info
    else:
        logging.error("Error: Unable to fetch data. Status code: " + str(response.status_code))
        return []

def get_train_disruptions():
    api_key = os.getenv('API_KEY')
    url = "https://datamall2.mytransport.sg/ltaodataservice/TrainServiceAlerts"
    headers = {
        'AccountKey': api_key,
        'accept': 'application/json'
    }

    print("Fetching train disruptions...")
    print(f"URL: {url}")
    print(f"Headers: {headers}")

    try:
        response = requests.get(url, headers=headers)
        print(f"Response status code: {response.status_code}")
        print(f"Response content: {response.text}")

        response.raise_for_status()  # Raises an HTTPError for bad responses
        data = response.json()

        print("Parsed JSON data:")
        print(json.dumps(data, indent=2))

        disruptions = []
        content = ''

        if 'value' in data:
            print("'value' key found in data")
            if 'AffectedSegments' in data['value'] and data['value']['AffectedSegments']:
                print("Processing AffectedSegments...")
                for segment in data['value']['AffectedSegments']:
                    disruption = {
                        'Line': segment.get('Line', ''),
                        'Direction': segment.get('Direction', ''),
                        'Stations': segment.get('Stations', '').split(',')
                    }
                    disruptions.append(disruption)
                    print(f"Added disruption: {disruption}")

            if 'Message' in data['value'] and data['value']['Message']:
                print("Processing Message...")
                content = data['value']['Message'][0].get('Content', '')
                print(f"Content: {content}")

        if not disruptions and not content:
            print("No disruptions found")
            return "No Disruptions Today!"
        else:
            result = {
                'disruptions': disruptions,
                'content': content
            }
            print(f"Returning result: {result}")
            return result

    except requests.RequestException as e:
        print(f"Error fetching train disruptions: {e}")
        return None

def display_bus_arrivals(epd, draw, font, bus_info_A, bus_info_B):
    draw.rectangle((0, 0, epd.width, epd.height), fill=epd.WHITE)  # Clear the display
    y = 20  # Initial Y position for text
    column_offset = epd.width // 2  # Divide the screen into two columns

    draw.text((120, y),"Downstairs", font=font, fill=epd.BLACK)

    # Display for Bus Stop A (left column)
    for service_no, arrival_times in bus_info_A:
        draw.rectangle((20, y+50, 140, y + 110), fill=epd.BLACK)
        draw.text((50, y + 58), service_no, font=font, fill=epd.WHITE)

        x = 180
        for i, arrival in enumerate(arrival_times):
            timing = arrival[0]
            flag = arrival[1]
            arrival_str = str(timing)

            if flag == "SDA":
                draw.text((x, y + 55), arrival_str, font=font, fill=epd.YELLOW)
            elif flag == "LSD":
                draw.text((x, y + 55), arrival_str, font=font, fill=epd.RED)
            else:
                draw.text((x, y + 55), arrival_str, font=font, fill=epd.BLACK)

            text_width = font.getlength(arrival_str)
            x += int(text_width)

            if i < len(arrival_times) - 1:
                sep = " | "
                draw.text((x, y + 55), sep, font=font, fill=epd.BLACK)
                x += int(font.getlength(sep))
        y += 70
        #times_text = " | ".join(map(str, arrival_times))
        #draw.text((180, y + 55), times_text, font=font, fill=epd.BLACK)
        #y += 70

    y = 20  # Reset Y position for the right column

    draw.text((120+column_offset, y),"Opposite", font=font, fill=epd.BLACK)

    # Display for Bus Stop B (right column)
    for service_no, arrival_times in bus_info_B:
        draw.rectangle((20 + column_offset, y+50, 140 + column_offset, y + 110), fill=epd.BLACK)
        draw.text((50 + column_offset, y + 58), service_no, font=font, fill=epd.WHITE)
        x = 180 + column_offset
        for i, arrival in enumerate(arrival_times):
            timing = arrival[0]
            flag = arrival[1]
            arrival_str = str(timing)

            if flag == "SDA":
                draw.text((x, y + 55), arrival_str, font=font, fill=epd.YELLOW)
            elif flag == "LSD":
                draw.text((x, y + 55), arrival_str, font=font, fill=epd.RED)
            else:
                draw.text((x, y + 55), arrival_str, font=font, fill=epd.BLACK)

            text_width = font.getlength(arrival_str)
            x += int(text_width)

            if i < len(arrival_times) - 1:
                sep = " | "
                draw.text((x, y + 55), sep, font=font, fill=epd.BLACK)
                x += int(font.getlength(sep))
        y += 70
        #times_text = " | ".join(map(str, arrival_times))
        #draw.text((180 + column_offset, y + 55), times_text, font=font, fill=epd.BLACK)
        #y += 70

    epd.display(epd.getbuffer(Himage))

try:
    logging.info("Bus Arrival Display on E-Ink")
    epd = epd7in5h.EPD()

    logging.info("Init and Clear")
    epd.init()
    epd.Clear()

  # Using a larger and bold font
    font48 = ImageFont.truetype(os.path.join(picdir, 'OpenSans-Bold.ttf'), 32)
    Himage = Image.new('RGB', (epd.width, epd.height), epd.WHITE)
    draw = ImageDraw.Draw(Himage)

    api_key = os.getenv('API_KEY')
    bus_stop_code_A = os.getenv('BUS_STOP_CODE_A')
    bus_stop_code_B = os.getenv('BUS_STOP_CODE_B')

    while True:
        now = datetime.now()
        current_hour = now.hour

        if START_HOUR <= current_hour < END_HOUR:
            on_break_displayed = False
        #Display Bus Arrival
            bus_info_A = get_bus_arrival(api_key, bus_stop_code_A)
            bus_info_B = get_bus_arrival(api_key, bus_stop_code_B)
            time.sleep(30)
            display_bus_arrivals(epd, draw, font48, bus_info_A, bus_info_B)
        else:
            if not on_break_displayed:
                time.sleep(30)
                epd.init()
                epd.Clear()
                Himage_weather = Image.new('RGB', (epd.width, epd.height), epd.WHITE)
                weather_data = get_weather_information()
                draw = ImageDraw.Draw(Himage_weather)
                title_font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf', 32)
                text_font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf', 20)
                draw.text((20, 20), "4-Day Weather Forecast", font=title_font, fill=0)
                y = 80  # Starting Y position for forecast entries

                # Extract forecast list
                forecasts = weather_data["data"]["records"][0]["forecasts"]

                # Draw each day’s forecast
                for forecast in forecasts:
                    day = forecast["day"]
                    summary = forecast["forecast"]["summary"]
                    temp_low = forecast["temperature"]["low"]
                    temp_high = forecast["temperature"]["high"]
                    hum_low = forecast["relativeHumidity"]["low"]
                    hum_high = forecast["relativeHumidity"]["high"]

                    # Combine info for display
                    line1 = f"{day}: {summary}"
                    line2 = f"Temp: {temp_low}–{temp_high}°C   Humidity: {hum_low}-{hum_high}%"

                    # Draw the text
                    draw.text((30, y), line1, font=text_font, fill=0)
                    draw.text((30, y + 30), line2, font=text_font, fill=0)

                    # Optional separator line
                    draw.line((20, y + 70, epd.width - 20, y + 70), fill=0)
                    y += 100  # Move down for next forecast block

                # Send image to the e-paper display
                epd.display(epd.getbuffer(Himage_weather))
                epd.sleep()
                #epd.init()
                #epd.Clear()
                #draw.rectangle((0, 0, epd.width, epd.height), fill=epd.WHITE)
                #draw.text((epd.width // 2 - 120, epd.height // 2 - 24), "Taking a break", font=font48, fill=epd.BL>
                #epd.display(epd.getbuffer(Himage))
                on_break_displayed = True
                time.sleep(600)
            time.sleep(600)

except IOError as e:
    logging.error(e)

except KeyboardInterrupt:
    logging.info("Exiting...")
    epd.Clear()
    epd7in5h.epdconfig.module_exit(cleanup=True)
    exit()
