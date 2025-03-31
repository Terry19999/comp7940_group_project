FROM python
WORKDIR /APP
COPY ./app.py /APP
COPY ./requirements.txt /APP
RUN pip install update
RUN pip install -r requirements.txt

CMD python app.py