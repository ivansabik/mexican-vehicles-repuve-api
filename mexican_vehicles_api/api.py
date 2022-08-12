from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import LambdaFunctionUrlEvent, event_source

from mexican_vehicles_api.exceptions import VehicleNotFound
from mexican_vehicles_api.scraper import get_vehicle

logger = Logger(service="api")


@event_source(data_class=LambdaFunctionUrlEvent)
def handler(event: LambdaFunctionUrlEvent, context):
    logger.info("Processing event", extra={"event": event.__dict__})
    if event.query_string_parameters and event.query_string_parameters.get("plates"):
        license_plates = event.query_string_parameters["plates"]
        return _find_vehicle_by_license_plates(license_plates)


def _find_vehicle_by_license_plates(license_plates):
    try:
        response = get_vehicle(license_plates)
    except VehicleNotFound:
        response = {"plates": license_plates, "error_message": "Vehicle not found"}
    return response
