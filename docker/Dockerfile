# docker/Dockerfile
FROM nvcr.io/nvidia/tensorflow:25.01-tf2-py3

WORKDIR /work

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

CMD ["bash"]

