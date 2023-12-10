# open-adr-3
Building side research project with open ADR 3

### Docker setup notes for VTN server

Build VTN server app in docker image.
```bash
docker build -t openadr-3-app .
```

Run docker server app
```bash
docker run -d --name openadr-3-app -p 8000:8000 openadr-3-app
```

Stop docker app
```bash
docker stop openadr-3-app
```

Tail docker logs
```bash
docker logs -f openadr-3-app
```

Remove docker app
```bash
docker rm openadr-3-app
```

### Client VEN App
Install Python packages with pip

```bash
pip install httpx
```

Run client app
```bash
$ python client.py
```
