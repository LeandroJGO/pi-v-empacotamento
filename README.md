# PI V - Sistema de Monitoramento de Empacotamento

Projeto integrador com captura de vídeo por câmera IP, armazenamento de registros em SQLite, interface em Python e integração com WeMos D1 R1 ESP8266 via comunicação serial.

## Funcionalidades
- Conexão com câmera IP
- Gravação de vídeos
- Registro em banco SQLite
- Interface gráfica com dashboard
- Exclusão lógica e sincronização entre pasta e banco
- Comunicação serial com ESP8266

## Tecnologias utilizadas
- Python
- CustomTkinter
- OpenCV
- SQLite
- PySerial
- ESP8266 / WeMos D1 R1

## Estrutura
- `main.py`: aplicação principal
- `arduino/`: código do microcontrolador
- `requirements.txt`: dependências do projeto