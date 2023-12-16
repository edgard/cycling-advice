#!/usr/bin/env python3

import os
import sys
import logging
from datetime import datetime
import requests
import pytz
from dotenv import dotenv_values

# Thresholds
WEATHER_THRESHOLDS = {"temperature": 0, "high_wind_speed": 25, "moderate_wind_speed": 15, "heavy_rain": 3, "light_rain": 1, "heavy_snow": 5, "light_snow": 2}

# Constants
TELEGRAM_API_URL = "https://api.telegram.org/bot{}/sendMessage"
OPENWEATHER_API_URL = "https://api.openweathermap.org/data/2.5/onecall"

# Initialize config
CONFIG = {**dotenv_values(".env"), **os.environ}


def get_config_value(key):
    try:
        return CONFIG[key]
    except KeyError:
        logging.error("Missing configuration key: %s", key)
        sys.exit(1)


def load_configuration():
    lat, lon = map(float, get_config_value("LOCATION_COORDINATES").split(","))
    CONFIG.update({"latitude": lat, "longitude": lon, "local_timezone": get_config_value("LOCAL_TIMEZONE"), "openweather_api_key": get_config_value("OPENWEATHER_API_KEY"), "telegram_token": get_config_value("TELEGRAM_TOKEN"), "telegram_chats": get_config_value("TELEGRAM_CHATS").split(",")})


def send_telegram_message(message):
    telegram_api_url = TELEGRAM_API_URL.format(CONFIG["telegram_token"])
    for chat_id in CONFIG["telegram_chats"]:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            response = requests.post(telegram_api_url, data=payload, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error("Telegram chat ID %s: %s", chat_id, e)


def fetch_forecast():
    params = {"lat": CONFIG["latitude"], "lon": CONFIG["longitude"], "units": "metric", "exclude": "current,minutely", "appid": CONFIG["openweather_api_key"]}
    try:
        response = requests.get(OPENWEATHER_API_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error("Error fetching forecast: %s", e)
        sys.exit(1)


def calculate_metric(return_type, forecast, metric, sunrise_ts, sunset_ts):
    if return_type not in ["sum", "avg"]:
        return NotImplemented

    total, count = 0, 0
    for entry in forecast["hourly"]:
        if metric in entry and sunrise_ts <= entry["dt"] <= sunset_ts:
            total += entry[metric]
            count += 1

    if count == 0:
        return None

    return round(total, 2) if return_type == "sum" else round(total / count, 2)


def generate_report(forecast):
    timezone_api = pytz.timezone(forecast["timezone"])

    sunrise_ts = datetime.fromtimestamp(forecast["daily"][0]["sunrise"], timezone_api).timestamp()
    sunset_ts = datetime.fromtimestamp(forecast["daily"][0]["sunset"], timezone_api).timestamp()

    rain = calculate_metric("sum", forecast, "rain", sunrise_ts, sunset_ts)
    snow = calculate_metric("sum", forecast, "snow", sunrise_ts, sunset_ts)
    temp = calculate_metric("avg", forecast, "feels_like", sunrise_ts, sunset_ts)
    wind = calculate_metric("avg", forecast, "wind_speed", sunrise_ts, sunset_ts)

    advice = "Favorable cycling conditions."
    if (wind is not None and wind >= WEATHER_THRESHOLDS["high_wind_speed"]) or (rain is not None and rain > WEATHER_THRESHOLDS["heavy_rain"]) or (snow is not None and snow > WEATHER_THRESHOLDS["heavy_snow"]):
        advice = "Cycling not recommended due to extreme weather conditions."
    elif (temp is not None and temp <= WEATHER_THRESHOLDS["temperature"]) or (rain is not None and rain > WEATHER_THRESHOLDS["light_rain"]) or (snow is not None and snow > WEATHER_THRESHOLDS["light_snow"]) or (wind is not None and WEATHER_THRESHOLDS["moderate_wind_speed"] <= wind < WEATHER_THRESHOLDS["high_wind_speed"]):
        advice = "Cycling possible with caution."

    report = f"*Cycling Weather Conditions on {datetime.now(pytz.timezone(CONFIG['local_timezone'])).strftime('%d/%m/%Y')} between {datetime.fromtimestamp(sunrise_ts, timezone_api).strftime('%I:%M:%S%p')} and {datetime.fromtimestamp(sunset_ts, timezone_api).strftime('%I:%M:%S%p')}*"
    report += f"\n\n{advice}"

    if temp is not None:
        report += f"\n\nAverage Feels Like: *{temp}*°C"
    if wind is not None:
        report += f"\nAverage Wind Speed: *{wind}*km/h"
    if rain is not None:
        report += f"\nTotal Rain: *{rain}*mm"
    if snow is not None:
        report += f"\nTotal Snow: *{snow}*mm"

    return report


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    load_configuration()

    send_telegram_message(generate_report(fetch_forecast()))


if __name__ == "__main__":
    main()
