import base64
import re

import tenacity
from aws_lambda_powertools import Logger
from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from mexican_vehicles_api.captcha_solver.testing import solver
from mexican_vehicles_api.exceptions import TransientError, VehicleNotFound
from mexican_vehicles_api.utils import get_chrome_webdriver

logger = Logger(service="scraper")

MAPPING = {
    0: {"column_name": "make", "english_description": "Make"},
    1: {"column_name": "model", "english_description": "Model"},
    2: {"column_name": "year", "english_description": "Year"},
    3: {"column_name": "classification", "english_description": "Classification"},
    4: {"column_name": "type", "english_description": "Type"},
    7: {"column_name": "license_plates", "english_description": "License Plates"},
    8: {"column_name": "doors", "english_description": "Number of doors"},
    9: {"column_name": "origin_country", "english_description": "Country of origin"},
    10: {"column_name": "version", "english_description": "Version"},
    14: {"column_name": "assembly_plant_location", "english_description": "Assemby Plant Location"},
    19: {"column_name": "state", "english_description": "State"},
}


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(TransientError),
    stop=tenacity.stop_after_attempt(15),
)
def get_vehicle(license_plates):
    logger.info("Attempting to retrieve data", extra={"plates": license_plates})
    driver = get_chrome_webdriver()
    driver.get("http://www2.repuve.gob.mx:8080/ciudadania/consulta/")

    element = driver.find_element("xpath", '//*[@id="modalReemplacamiento"]/div/div/div[3]/button')
    element.click()

    # Save the captcha to local disk and solve
    element = driver.find_element(
        "xpath", "/html/body/main/form/div[1]/div/div[3]/div[5]/div[1]/img"
    )
    img_captcha_base64 = driver.execute_async_script(
        """
        var ele = arguments[0], callback = arguments[1];
        ele.addEventListener('load', function fn(){
          ele.removeEventListener('load', fn, false);
          var cnv = document.createElement('canvas');
          cnv.width = this.width; cnv.height = this.height;
          cnv.getContext('2d').drawImage(this, 0, 0);
          callback(cnv.toDataURL('image/jpeg').substring(22));
        }, false);
        ele.dispatchEvent(new Event('load'));
        """,
        element,
    )
    with open(r"/tmp/jcaptcha.jpg", "wb") as f:
        f.write(base64.b64decode(img_captcha_base64))
    captcha_answer = solver.main("/tmp/jcaptcha.jpg")
    logger.info(f"Captcha solved", extra={"answer": captcha_answer})

    # Send form with license_plates and captcha
    driver.find_element("id", "placa").send_keys(license_plates)
    driver.find_element("id", "captcha").send_keys(captcha_answer)
    form = driver.find_element("xpath", "/html/body/main/form")
    form.submit()

    # Validate results after submitting the form
    if "El texto de la imagen y el que captura" in driver.page_source:
        raise TransientError("Invalid captcha answer")
    if "PLACA no encontrada" in driver.page_source:
        raise VehicleNotFound(f"No vehicle was found wih license license plates {license_plates}")

    # Write HTML to local disk
    html_output_path = f"/tmp/{license_plates}.html"
    with open(html_output_path, "w") as f:
        f.write(driver.page_source)
        logger.info(f"Wrote output HTML", extra={"path": html_output_path})
    output_html = str(driver.page_source)

    # Parse the table with vehicle information
    # Marca:	TOYOTA
    # Modelo:	RAV4
    # Año Modelo:	2019
    # Clase:	CAMIONETA
    # Tipo:	SUV
    # Número de Identificación Vehicular (NIV):	JTMR13FV2KD030511
    # Número de Constancia de Inscripción (NCI):	2PO99KBM
    # Placa:	FZX865B
    # Número de puertas:	5 PUERTAS
    # País de origen:	JAPON
    # Versión:	AWD XLE
    # Desplazamiento (cc/L):	2.5L
    # Número de cilindros:	L4
    # Número de ejes:
    # Planta de ensamble:	JAPON
    # Datos complementarios:	4 PTAS SUV JAPON 2.5L, L4
    # Institución que lo inscribió:	TOYOTA MOTOR SALES DE MEXICO, S. DE R.L. DE C.V.
    # Fecha de inscripción:	15/07/2019
    # Hora de inscripción:	11:35:54
    # Entidad que emplacó	DURANGO
    # Fecha de emplacado:	20/07/2019
    # Fecha de última actualización:	22/07/2019
    # Folio de Constancia de Inscripción:	13453671
    # Observaciones:	ALTA DE VEHICULO
    soup = BeautifulSoup(output_html, "html.parser")
    table = soup.find("table")
    table_body = table.find("tbody")
    rows = table_body.find_all("tr")
    vehicle_data = {}
    for row_number, row in enumerate(rows):
        if not row_number in MAPPING.keys():
            continue
        cols = row.find_all("td")
        cols = [ele.text.strip().replace(":", "") for ele in cols]
        cols = [ele for ele in cols if ele]
        row_description = cols[0]
        try:
            row_value = cols[1]
        except IndexError:
            logger.error(f"Failed processing values {cols}")
            row_value = ""

        # Remove repeated white spaces
        row_value = " ".join(row_value.split())

        # Cleanup fields
        if "puertas" in row_description:
            row_value = row_value.replace(" PUERTAS", "")

        column_name = MAPPING[row_number]["column_name"]
        vehicle_data[column_name] = row_value

    has_stolen_report = len(soup.body.findAll(text="Con Reporte de Robo")) > 0
    vehicle_data["has_stolen_report"] = has_stolen_report

    # Type casting
    if vehicle_data["doors"]:
        doors = re.sub("[^0-9]", "", vehicle_data["doors"])
        vehicle_data["doors"] = int(doors)
    if vehicle_data["doors"]:
        vehicle_data["year"] = int(vehicle_data["year"])

    return vehicle_data


if __name__ == "__main__":
    license_plates = "driver.page_source"
    data = get_vehicle("WUC6944")
    logger.info("Finished", extra={"data": data})
