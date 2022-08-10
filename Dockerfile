FROM umihico/aws-lambda-selenium-python:latest
COPY ./ ./
RUN pip install -r requirements.txt && pip install -e .
CMD [ "mexican_vehicles_api.api.handler" ]
