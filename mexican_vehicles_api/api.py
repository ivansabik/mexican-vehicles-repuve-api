from aws_lambda_powertools import Logger
from flask import Flask

from mexican_vehicles_api.scraper import get_vehicle

app = Flask(__name__)
logger = Logger(service="scraper")


@app.get("/vehicles/<license_plates>")
def find_vehicle_by_license_plates(license_plates):
    response = get_vehicle(license_plates)
    return response, 200
