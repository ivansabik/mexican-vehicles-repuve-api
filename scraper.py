import base64
import time

import tenacity
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from captcha_solver.testing import solver

PLATES = [
    "PYL9947",
    "F19AEM",
    "456ZDT",
    "760TLY",
    "148YPM",
    "SLS3560",
    "RJ43486",
    "5274TGF",
    "JJY2623",
]


class TransientError(Exception):
    pass


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(TransientError),
    stop=tenacity.stop_after_attempt(10),
)
def submit_form(plates):
    options = Options()
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    # options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--single-process")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    driver.get("http://www2.repuve.gob.mx:8080/ciudadania/consulta/")

    element = driver.find_element_by_xpath('//*[@id="modalReemplacamiento"]/div/div/div[3]/button')
    element.click()

    element = driver.find_element_by_xpath(
        "/html/body/main/form/div[1]/div/div[3]/div[5]/div[1]/img"
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
    print(f"Captcha answer: {captcha_answer}")

    driver.find_element_by_id("placa").send_keys(plates)
    driver.find_element_by_id("captcha").send_keys(captcha_answer)

    form = driver.find_element_by_xpath("/html/body/main/form")
    form.submit()

    if "El texto de la imagen y el que captura" in driver.page_source:
        driver.close()
        raise TransientError("Invalid captcha answer")

    if "PLACA no encontrada" in driver.page_source:
        driver.close()
        raise Exception("Not found")

    with open(f"/tmp/{plates}.html", "w") as f:
        f.write(driver.page_source)
        print(f"Wrote /tmp/{plates}.html")
    driver.close()


def main():
    plates = PLATES[-1]
    submit_form(plates)


if __name__ == "__main__":
    main()
